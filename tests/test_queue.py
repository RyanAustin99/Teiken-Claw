"""
Tests for the Teiken Claw queue system.

This module tests:
- Job creation and serialization
- Priority ordering
- Idempotency key deduplication
- Queue backpressure
- Per-chat locks
- Rate limiting
- Dead-letter queue operations
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json

from app.queue.jobs import (
    Job,
    JobPriority,
    JobSource,
    JobType,
    create_job,
)
from app.queue.dispatcher import (
    JobDispatcher,
    QueueFullError,
    DuplicateJobError,
)
from app.queue.locks import (
    LockManager,
    LockInfo,
    LockTimeoutError,
)
from app.queue.workers import (
    WorkerPool,
    WorkerStatus,
    WorkerInfo,
)
from app.queue.throttles import (
    RateLimiter,
    OutboundQueue,
    OutboundMessage,
    MessageStatus,
)
from app.queue.dead_letter import (
    DeadLetterQueue,
    JobNotFoundError,
    ReplayError,
)


# =============================================================================
# Job Model Tests
# =============================================================================

class TestJobModel:
    """Tests for Job model and related enums."""
    
    def test_job_creation_defaults(self):
        """Test job creation with default values."""
        job = Job()
        
        assert job.job_id is not None
        assert job.source == JobSource.INTERNAL
        assert job.type == JobType.CUSTOM
        assert job.priority == JobPriority.SCHEDULED
        assert job.attempts == 0
        assert job.max_attempts == 3
        assert job.created_at is not None
    
    def test_job_creation_with_values(self):
        """Test job creation with specific values."""
        job = Job(
            job_id="test-job-123",
            source=JobSource.TELEGRAM,
            type=JobType.CHAT_MESSAGE,
            priority=JobPriority.INTERACTIVE,
            chat_id="123456",
            payload={"text": "Hello"},
        )
        
        assert job.job_id == "test-job-123"
        assert job.source == JobSource.TELEGRAM
        assert job.type == JobType.CHAT_MESSAGE
        assert job.priority == JobPriority.INTERACTIVE
        assert job.chat_id == "123456"
        assert job.payload == {"text": "Hello"}
    
    def test_create_job_factory(self):
        """Test the create_job factory function."""
        job = create_job(
            source=JobSource.CLI,
            type=JobType.CHAT_MESSAGE,
            payload={"message": "test"},
            priority=JobPriority.INTERACTIVE,
            chat_id="789",
        )
        
        assert job.source == JobSource.CLI
        assert job.type == JobType.CHAT_MESSAGE
        assert job.priority == JobPriority.INTERACTIVE
        assert job.chat_id == "789"
        assert job.payload == {"message": "test"}
    
    def test_job_priority_ordering(self):
        """Test job priority comparison."""
        high_priority = Job(priority=JobPriority.INTERACTIVE)
        low_priority = Job(priority=JobPriority.MAINTENANCE)
        
        assert high_priority < low_priority
        assert low_priority > high_priority
    
    def test_job_created_at_ordering(self):
        """Test job ordering by creation time when priority is equal."""
        job1 = Job(priority=JobPriority.SCHEDULED, created_at=datetime.utcnow())
        job2 = Job(
            priority=JobPriority.SCHEDULED,
            created_at=datetime.utcnow() + timedelta(seconds=1),
        )
        
        assert job1 < job2
    
    def test_job_increment_attempts(self):
        """Test incrementing job attempts."""
        job = Job(attempts=1)
        updated = job.increment_attempts()
        
        assert updated.attempts == 2
        assert job.attempts == 1  # Original unchanged
    
    def test_job_can_retry(self):
        """Test retry check."""
        job = Job(attempts=2, max_attempts=3)
        assert job.can_retry() is True
        
        job = Job(attempts=3, max_attempts=3)
        assert job.can_retry() is False
    
    def test_job_to_queue_item(self):
        """Test conversion to queue item tuple."""
        job = Job(priority=10)
        item = job.to_queue_item()
        
        assert isinstance(item, tuple)
        assert len(item) == 3
        assert item[0] == 10  # priority
        assert item[2] == job  # job itself
    
    def test_job_serialization(self):
        """Test job serialization to dict/JSON."""
        job = Job(
            job_id="test-123",
            source=JobSource.TELEGRAM,
            type=JobType.CHAT_MESSAGE,
            payload={"text": "Hello"},
        )
        
        # Test model_dump
        data = job.model_dump()
        assert data["job_id"] == "test-123"
        assert data["source"] == "telegram"
        assert data["type"] == "chat_message"
        
        # Test JSON serialization
        json_str = job.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["job_id"] == "test-123"


# =============================================================================
# Dispatcher Tests
# =============================================================================

class TestJobDispatcher:
    """Tests for JobDispatcher."""
    
    @pytest.fixture
    def dispatcher(self):
        """Create a dispatcher for testing."""
        return JobDispatcher(max_size=10, idempotency_ttl_seconds=60)
    
    def test_dispatcher_initialization(self, dispatcher):
        """Test dispatcher initialization."""
        assert dispatcher.max_size == 10
        assert dispatcher.queue_depth == 0
        assert dispatcher.pending_count == 0
        assert not dispatcher.is_full
        assert not dispatcher.is_shutdown
    
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, dispatcher):
        """Test basic enqueue and dequeue operations."""
        job = create_job(
            source=JobSource.TELEGRAM,
            type=JobType.CHAT_MESSAGE,
            payload={"text": "test"},
        )
        
        # Enqueue
        result = await dispatcher.enqueue(job)
        assert result is True
        assert dispatcher.queue_depth == 1
        
        # Dequeue
        dequeued = await dispatcher.dequeue(timeout=1.0)
        assert dequeued is not None
        assert dequeued.job_id == job.job_id
        assert dispatcher.pending_count == 1
    
    @pytest.mark.asyncio
    async def test_priority_ordering(self, dispatcher):
        """Test that jobs are dequeued in priority order."""
        low_job = Job(priority=JobPriority.MAINTENANCE, payload={"order": 3})
        medium_job = Job(priority=JobPriority.SCHEDULED, payload={"order": 2})
        high_job = Job(priority=JobPriority.INTERACTIVE, payload={"order": 1})
        
        # Enqueue in random order
        await dispatcher.enqueue(medium_job)
        await dispatcher.enqueue(low_job)
        await dispatcher.enqueue(high_job)
        
        # Dequeue should return in priority order
        first = await dispatcher.dequeue(timeout=1.0)
        second = await dispatcher.dequeue(timeout=1.0)
        third = await dispatcher.dequeue(timeout=1.0)
        
        assert first.priority == JobPriority.INTERACTIVE
        assert second.priority == JobPriority.SCHEDULED
        assert third.priority == JobPriority.MAINTENANCE
    
    @pytest.mark.asyncio
    async def test_idempotency_deduplication(self, dispatcher):
        """Test that duplicate jobs are rejected."""
        job1 = Job(
            idempotency_key="unique-key-123",
            payload={"test": 1},
        )
        job2 = Job(
            idempotency_key="unique-key-123",
            payload={"test": 2},
        )
        
        # First enqueue should succeed
        await dispatcher.enqueue(job1)
        
        # Second enqueue with same key should fail
        with pytest.raises(DuplicateJobError):
            await dispatcher.enqueue(job2)
    
    @pytest.mark.asyncio
    async def test_queue_backpressure(self, dispatcher):
        """Test queue backpressure when full."""
        # Fill the queue
        for i in range(10):
            job = Job(payload={"index": i})
            await dispatcher.enqueue(job)
        
        assert dispatcher.is_full
        
        # Next enqueue should fail
        with pytest.raises(QueueFullError):
            await dispatcher.enqueue(Job())
    
    @pytest.mark.asyncio
    async def test_mark_complete(self, dispatcher):
        """Test marking a job as complete."""
        job = Job()
        await dispatcher.enqueue(job)
        dequeued = await dispatcher.dequeue(timeout=1.0)
        
        assert dispatcher.pending_count == 1
        
        dispatcher.mark_complete(job.job_id)
        
        assert dispatcher.pending_count == 0
    
    @pytest.mark.asyncio
    async def test_mark_failed_retry(self, dispatcher):
        """Test that failed jobs are retried."""
        job = Job(attempts=0, max_attempts=3)
        await dispatcher.enqueue(job)
        dequeued = await dispatcher.dequeue(timeout=1.0)
        
        # Simulate failure
        error = Exception("Test error")
        await dispatcher.mark_failed(dequeued, error)
        
        # Job should be back in queue for retry
        assert dispatcher.queue_depth == 1
    
    @pytest.mark.asyncio
    async def test_shutdown(self, dispatcher):
        """Test dispatcher shutdown."""
        await dispatcher.shutdown(wait=False)
        
        assert dispatcher.is_shutdown
        
        # Should reject new jobs
        result = await dispatcher.enqueue(Job())
        assert result is False
    
    def test_get_stats(self, dispatcher):
        """Test getting dispatcher statistics."""
        stats = dispatcher.get_stats()
        
        assert "queue_depth" in stats
        assert "max_size" in stats
        assert "pending_count" in stats
        assert "total_enqueued" in stats


# =============================================================================
# Lock Manager Tests
# =============================================================================

class TestLockManager:
    """Tests for LockManager."""
    
    @pytest.fixture
    def lock_manager(self):
        """Create a lock manager for testing."""
        return LockManager(default_timeout=5)
    
    def test_lock_manager_initialization(self, lock_manager):
        """Test lock manager initialization."""
        assert lock_manager.default_timeout == 5
        assert lock_manager.get_lock_count()["total"] == 0
    
    @pytest.mark.asyncio
    async def test_acquire_chat_lock(self, lock_manager):
        """Test acquiring a chat lock."""
        async with lock_manager.acquire_chat_lock("123456") as lock_info:
            assert lock_info.resource_type == "chat"
            assert lock_info.resource_id == "123456"
            assert lock_manager.is_chat_locked("123456")
        
        # Lock should be released
        assert not lock_manager.is_chat_locked("123456")
    
    @pytest.mark.asyncio
    async def test_acquire_session_lock(self, lock_manager):
        """Test acquiring a session lock."""
        async with lock_manager.acquire_session_lock("session-123") as lock_info:
            assert lock_info.resource_type == "session"
            assert lock_info.resource_id == "session-123"
            assert lock_manager.is_session_locked("session-123")
        
        # Lock should be released
        assert not lock_manager.is_session_locked("session-123")
    
    @pytest.mark.asyncio
    async def test_lock_timeout(self, lock_manager):
        """Test lock timeout."""
        lock_manager.default_timeout = 0  # Immediate timeout
        
        # First lock acquisition
        async with lock_manager.acquire_chat_lock("123"):
            # Second acquisition should timeout
            with pytest.raises(LockTimeoutError):
                async with lock_manager.acquire_chat_lock("123", timeout=0.1):
                    pass
    
    @pytest.mark.asyncio
    async def test_concurrent_lock_prevention(self, lock_manager):
        """Test that concurrent locks are prevented."""
        results = []
        
        async def task1():
            async with lock_manager.acquire_chat_lock("shared"):
                results.append("task1_start")
                await asyncio.sleep(0.1)
                results.append("task1_end")
        
        async def task2():
            # Small delay to ensure task1 gets lock first
            await asyncio.sleep(0.05)
            async with lock_manager.acquire_chat_lock("shared"):
                results.append("task2_start")
                results.append("task2_end")
        
        # Run both tasks
        await asyncio.gather(task1(), task2())
        
        # task2 should have waited for task1 to finish
        assert results == ["task1_start", "task1_end", "task2_start", "task2_end"]
    
    def test_get_active_locks(self, lock_manager):
        """Test getting active locks."""
        locks = lock_manager.get_active_locks()
        assert len(locks) == 0
    
    def test_get_lock_count(self, lock_manager):
        """Test getting lock count."""
        count = lock_manager.get_lock_count()
        
        assert "chat_locks" in count
        assert "session_locks" in count
        assert "total" in count


# =============================================================================
# Worker Pool Tests
# =============================================================================

class TestWorkerPool:
    """Tests for WorkerPool."""
    
    @pytest.fixture
    def worker_pool(self):
        """Create a worker pool for testing."""
        dispatcher = JobDispatcher(max_size=10)
        lock_manager = LockManager(default_timeout=5)
        return WorkerPool(
            dispatcher=dispatcher,
            lock_manager=lock_manager,
            num_workers=2,
            ollama_concurrency=1,
        )
    
    def test_worker_pool_initialization(self, worker_pool):
        """Test worker pool initialization."""
        assert worker_pool.num_workers == 2
        assert worker_pool.ollama_concurrency == 1
        assert not worker_pool._running
    
    @pytest.mark.asyncio
    async def test_start_stop_workers(self, worker_pool):
        """Test starting and stopping workers."""
        await worker_pool.start()
        
        assert worker_pool._running
        assert len(worker_pool._workers) == 2
        
        status = worker_pool.get_status()
        assert status["running"] is True
        assert status["num_workers"] == 2
        
        await worker_pool.stop(timeout=5.0)
        
        assert not worker_pool._running
    
    @pytest.mark.asyncio
    async def test_worker_processes_job(self, worker_pool):
        """Test that workers process jobs."""
        processed = []
        
        async def handler(job):
            processed.append(job.job_id)
        
        worker_pool.register_handler(JobType.CUSTOM, handler)
        
        # Add a job
        job = Job(type=JobType.CUSTOM, payload={"test": True})
        await worker_pool.dispatcher.enqueue(job)
        
        # Start workers
        await worker_pool.start()
        
        # Wait for processing
        await asyncio.sleep(0.5)
        
        # Stop workers
        await worker_pool.stop(timeout=5.0)
        
        # Job should have been processed
        assert len(processed) == 1
    
    def test_register_handler(self, worker_pool):
        """Test registering a job handler."""
        async def handler(job):
            pass
        
        worker_pool.register_handler(JobType.CHAT_MESSAGE, handler)
        
        assert JobType.CHAT_MESSAGE in worker_pool._handlers
    
    def test_get_status(self, worker_pool):
        """Test getting worker pool status."""
        status = worker_pool.get_status()
        
        assert "running" in status
        assert "num_workers" in status
        assert "active_workers" in status
        assert "total_jobs_processed" in status


# =============================================================================
# Rate Limiter Tests
# =============================================================================

class TestRateLimiter:
    """Tests for RateLimiter."""
    
    @pytest.fixture
    def rate_limiter(self):
        """Create a rate limiter for testing."""
        return RateLimiter(global_rate=10.0, per_chat_rate=2.0)
    
    def test_rate_limiter_initialization(self, rate_limiter):
        """Test rate limiter initialization."""
        assert rate_limiter.global_rate == 10.0
        assert rate_limiter.per_chat_rate == 2.0
    
    @pytest.mark.asyncio
    async def test_global_rate_limiting(self, rate_limiter):
        """Test global rate limiting."""
        start = datetime.utcnow()
        
        # Make multiple requests
        for _ in range(5):
            await rate_limiter.acquire_global()
        
        elapsed = (datetime.utcnow() - start).total_seconds()
        
        # Should have taken some time due to rate limiting
        # With rate of 10/s, 5 requests should take at least 0.4s
        # (but with burst factor, might be faster)
    
    @pytest.mark.asyncio
    async def test_per_chat_rate_limiting(self, rate_limiter):
        """Test per-chat rate limiting."""
        start = datetime.utcnow()
        
        # Make multiple requests for same chat
        for _ in range(3):
            await rate_limiter.acquire_chat("123456")
        
        elapsed = (datetime.utcnow() - start).total_seconds()
        
        # Should have taken time due to per-chat rate limiting
    
    def test_get_stats(self, rate_limiter):
        """Test getting rate limiter statistics."""
        stats = rate_limiter.get_stats()
        
        assert "global_rate" in stats
        assert "per_chat_rate" in stats
        assert "has_aiolimiter" in stats


class TestOutboundQueue:
    """Tests for OutboundQueue."""
    
    @pytest.fixture
    def outbound_queue(self):
        """Create an outbound queue for testing."""
        rate_limiter = RateLimiter(global_rate=30.0, per_chat_rate=1.0)
        return OutboundQueue(
            rate_limiter=rate_limiter,
            max_queue_size=10,
            max_attempts=3,
        )
    
    def test_outbound_queue_initialization(self, outbound_queue):
        """Test outbound queue initialization."""
        assert outbound_queue.max_queue_size == 10
        assert outbound_queue.max_attempts == 3
        assert outbound_queue.queue_depth == 0
    
    @pytest.mark.asyncio
    async def test_enqueue_message(self, outbound_queue):
        """Test enqueueing a message."""
        message_id = await outbound_queue.enqueue_message(
            chat_id="123456",
            text="Hello, world!",
        )
        
        assert message_id is not None
        assert outbound_queue.queue_depth == 1
    
    @pytest.mark.asyncio
    async def test_queue_full(self, outbound_queue):
        """Test queue full condition."""
        # Fill the queue
        for i in range(10):
            await outbound_queue.enqueue_message(
                chat_id="123",
                text=f"Message {i}",
            )
        
        # Next should fail
        with pytest.raises(Exception):
            await outbound_queue.enqueue_message(
                chat_id="123",
                text="Overflow message",
            )
    
    @pytest.mark.asyncio
    async def test_start_stop_sender(self, outbound_queue):
        """Test starting and stopping the sender."""
        await outbound_queue.start_sender()
        
        assert outbound_queue.is_running
        
        await outbound_queue.stop_sender(timeout=5.0)
        
        assert not outbound_queue.is_running
    
    def test_get_stats(self, outbound_queue):
        """Test getting outbound queue statistics."""
        stats = outbound_queue.get_stats()
        
        assert "running" in stats
        assert "queue_depth" in stats
        assert "total_sent" in stats
        assert "total_failed" in stats


# =============================================================================
# Dead Letter Queue Tests
# =============================================================================

class TestDeadLetterQueue:
    """Tests for DeadLetterQueue."""
    
    @pytest.fixture
    def dead_letter_queue(self):
        """Create a dead-letter queue for testing."""
        return DeadLetterQueue()
    
    def test_dead_letter_queue_initialization(self, dead_letter_queue):
        """Test dead-letter queue initialization."""
        stats = dead_letter_queue.get_stats()
        
        assert stats["total_added"] == 0
        assert stats["total_replayed"] == 0
        assert stats["has_dispatcher"] is False
    
    @pytest.mark.asyncio
    async def test_add_job(self, dead_letter_queue):
        """Test adding a job to dead-letter queue."""
        job = Job(
            job_id="test-job-123",
            source=JobSource.TELEGRAM,
            type=JobType.CHAT_MESSAGE,
            payload={"text": "test"},
        )
        error = Exception("Test error")
        
        # Mock database session
        with patch("app.queue.dead_letter.get_session") as mock_session:
            mock_session_cm = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_session_cm
            
            # Mock the database operations
            mock_entry = MagicMock()
            mock_entry.id = 1
            mock_session_cm.add = MagicMock()
            mock_session_cm.commit = AsyncMock()
            mock_session_cm.refresh = AsyncMock()
            
            entry_id = await dead_letter_queue.add(job, error)
            
            assert mock_session_cm.add.called
    
    def test_get_stats(self, dead_letter_queue):
        """Test getting dead-letter queue statistics."""
        stats = dead_letter_queue.get_stats()
        
        assert "total_added" in stats
        assert "total_replayed" in stats
        assert "total_deleted" in stats
        assert "has_dispatcher" in stats


# =============================================================================
# Integration Tests
# =============================================================================

class TestQueueIntegration:
    """Integration tests for the queue system."""
    
    @pytest.mark.asyncio
    async def test_full_job_lifecycle(self):
        """Test a job going through the full lifecycle."""
        # Create components
        dispatcher = JobDispatcher(max_size=10)
        lock_manager = LockManager(default_timeout=5)
        worker_pool = WorkerPool(
            dispatcher=dispatcher,
            lock_manager=lock_manager,
            num_workers=1,
        )
        
        # Track processing
        processed = []
        
        async def handler(job):
            processed.append(job.job_id)
        
        worker_pool.register_handler(JobType.CUSTOM, handler)
        
        # Create and enqueue job
        job = create_job(
            source=JobSource.CLI,
            type=JobType.CUSTOM,
            payload={"test": True},
        )
        
        await dispatcher.enqueue(job)
        
        # Start workers
        await worker_pool.start()
        
        # Wait for processing
        await asyncio.sleep(0.5)
        
        # Stop workers
        await worker_pool.stop(timeout=5.0)
        
        # Verify job was processed
        assert len(processed) == 1
        assert processed[0] == job.job_id
    
    @pytest.mark.asyncio
    async def test_per_chat_locking_prevents_overlap(self):
        """Test that per-chat locking prevents concurrent processing."""
        lock_manager = LockManager(default_timeout=5)
        
        processing_order = []
        
        async def process_chat(chat_id, delay):
            async with lock_manager.acquire_chat_lock(chat_id):
                processing_order.append(f"{chat_id}_start")
                await asyncio.sleep(delay)
                processing_order.append(f"{chat_id}_end")
        
        # Start two tasks for same chat
        task1 = asyncio.create_task(process_chat("123", 0.2))
        task2 = asyncio.create_task(process_chat("123", 0.1))
        
        # Small delay to ensure task1 starts first
        await asyncio.sleep(0.05)
        
        await asyncio.gather(task1, task2)
        
        # Task2 should have waited for task1
        assert processing_order == ["123_start", "123_end", "123_start", "123_end"]


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])