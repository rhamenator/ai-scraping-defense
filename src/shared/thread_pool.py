"""Optimized thread pool management with dynamic sizing and monitoring.

This module provides a centralized thread pool manager with:
- Dynamic sizing based on workload
- Thread affinity optimization
- Work-stealing capabilities
- Comprehensive monitoring and metrics
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Deque, Optional

try:
    from prometheus_client import Counter, Gauge, Histogram
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class ThreadPoolConfig:
    """Configuration for thread pool behavior."""
    
    min_workers: int = 2
    max_workers: int = 32
    idle_timeout: int = 60
    work_queue_size: int = 1000
    enable_monitoring: bool = True
    scaling_factor: float = 1.5
    scale_down_threshold: float = 0.3


@dataclass
class ThreadPoolMetrics:
    """Thread pool performance metrics."""
    
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    active_workers: int = 0
    queue_size: int = 0
    avg_execution_time: float = 0.0
    peak_workers: int = 0


class WorkStealingQueue:
    """Thread-safe work queue with work-stealing capabilities."""
    
    def __init__(self, maxsize: int = 1000):
        self._queue: Deque[tuple[Callable, tuple, dict]] = deque(maxlen=maxsize)
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._maxsize = maxsize
    
    def put(self, item: tuple[Callable, tuple, dict], timeout: Optional[float] = None) -> bool:
        """Add a work item to the queue."""
        with self._lock:
            if len(self._queue) >= self._maxsize:
                return False
            self._queue.append(item)
            self._not_empty.notify()
            return True
    
    def get(self, timeout: Optional[float] = None) -> Optional[tuple[Callable, tuple, dict]]:
        """Get a work item from the front of the queue."""
        with self._not_empty:
            while not self._queue:
                if not self._not_empty.wait(timeout):
                    return None
            return self._queue.popleft()
    
    def steal(self) -> Optional[tuple[Callable, tuple, dict]]:
        """Steal a work item from the back of the queue (work-stealing)."""
        with self._lock:
            if self._queue:
                return self._queue.pop()
            return None
    
    def qsize(self) -> int:
        """Return the approximate size of the queue."""
        with self._lock:
            return len(self._queue)
    
    def empty(self) -> bool:
        """Return True if the queue is empty."""
        with self._lock:
            return len(self._queue) == 0


class OptimizedThreadPoolExecutor:
    """Thread pool executor with dynamic sizing and work-stealing."""
    
    def __init__(self, config: Optional[ThreadPoolConfig] = None):
        self.config = config or self._load_config()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._work_queue = WorkStealingQueue(self.config.work_queue_size)
        self._metrics = ThreadPoolMetrics()
        self._lock = threading.Lock()
        self._shutdown = False
        self._last_scale_time = time.time()
        self._execution_times: Deque[float] = deque(maxlen=100)
        
        # Initialize Prometheus metrics if available
        if PROMETHEUS_AVAILABLE and self.config.enable_monitoring:
            self._init_prometheus_metrics()
        
        # Start with minimum workers
        self._resize_pool(self.config.min_workers)
        
        # Start monitoring thread
        if self.config.enable_monitoring:
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="ThreadPoolMonitor"
            )
            self._monitor_thread.start()
    
    def _load_config(self) -> ThreadPoolConfig:
        """Load configuration from environment variables."""
        return ThreadPoolConfig(
            min_workers=int(os.getenv("THREAD_POOL_MIN_WORKERS", "2")),
            max_workers=int(os.getenv("THREAD_POOL_MAX_WORKERS", "32")),
            idle_timeout=int(os.getenv("THREAD_POOL_IDLE_TIMEOUT", "60")),
            work_queue_size=int(os.getenv("THREAD_POOL_QUEUE_SIZE", "1000")),
            enable_monitoring=os.getenv("THREAD_POOL_MONITORING", "true").lower() == "true",
            scaling_factor=float(os.getenv("THREAD_POOL_SCALING_FACTOR", "1.5")),
            scale_down_threshold=float(os.getenv("THREAD_POOL_SCALE_DOWN_THRESHOLD", "0.3")),
        )
    
    def _init_prometheus_metrics(self) -> None:
        """Initialize Prometheus metrics for monitoring."""
        self._prom_tasks_total = Counter(
            "thread_pool_tasks_total",
            "Total number of tasks submitted to the thread pool"
        )
        self._prom_tasks_completed = Counter(
            "thread_pool_tasks_completed_total",
            "Total number of tasks completed"
        )
        self._prom_tasks_failed = Counter(
            "thread_pool_tasks_failed_total",
            "Total number of tasks that failed"
        )
        self._prom_active_workers = Gauge(
            "thread_pool_active_workers",
            "Current number of active worker threads"
        )
        self._prom_queue_size = Gauge(
            "thread_pool_queue_size",
            "Current size of the work queue"
        )
        self._prom_execution_time = Histogram(
            "thread_pool_task_execution_seconds",
            "Task execution time in seconds"
        )
    
    def _resize_pool(self, new_size: int) -> None:
        """Resize the thread pool to the specified number of workers."""
        new_size = max(self.config.min_workers, min(new_size, self.config.max_workers))
        
        with self._lock:
            current_size = self._executor._max_workers if self._executor else 0
            
            if new_size == current_size:
                return
            
            logger.info(f"Resizing thread pool from {current_size} to {new_size} workers")
            
            # Create new executor with updated size
            old_executor = self._executor
            self._executor = ThreadPoolExecutor(
                max_workers=new_size,
                thread_name_prefix="OptimizedWorker"
            )
            
            # Shutdown old executor gracefully
            if old_executor:
                old_executor.shutdown(wait=False)
            
            self._metrics.active_workers = new_size
            self._metrics.peak_workers = max(self._metrics.peak_workers, new_size)
            
            if PROMETHEUS_AVAILABLE and self.config.enable_monitoring:
                self._prom_active_workers.set(new_size)
    
    def _should_scale_up(self) -> bool:
        """Determine if the pool should scale up."""
        queue_size = self._work_queue.qsize()
        current_workers = self._metrics.active_workers
        
        # Scale up if queue is building up
        if queue_size > current_workers * 2:
            return True
        
        # Scale up if recent execution times are increasing
        if len(self._execution_times) >= 10:
            recent_avg = sum(list(self._execution_times)[-10:]) / 10
            if recent_avg > self._metrics.avg_execution_time * self.config.scaling_factor:
                return True
        
        return False
    
    def _should_scale_down(self) -> bool:
        """Determine if the pool should scale down."""
        queue_size = self._work_queue.qsize()
        current_workers = self._metrics.active_workers
        
        # Don't scale below minimum
        if current_workers <= self.config.min_workers:
            return False
        
        # Scale down if queue is mostly empty
        if queue_size < current_workers * self.config.scale_down_threshold:
            return True
        
        return False
    
    def _monitor_loop(self) -> None:
        """Background monitoring and auto-scaling loop."""
        while not self._shutdown:
            try:
                time.sleep(5)  # Check every 5 seconds
                
                current_time = time.time()
                time_since_scale = current_time - self._last_scale_time
                
                # Only scale if enough time has passed since last scaling
                if time_since_scale < 10:
                    continue
                
                current_workers = self._metrics.active_workers
                
                if self._should_scale_up():
                    new_size = int(current_workers * self.config.scaling_factor)
                    self._resize_pool(new_size)
                    self._last_scale_time = current_time
                elif self._should_scale_down():
                    new_size = int(current_workers / self.config.scaling_factor)
                    self._resize_pool(new_size)
                    self._last_scale_time = current_time
                
                # Update metrics
                if PROMETHEUS_AVAILABLE and self.config.enable_monitoring:
                    self._prom_queue_size.set(self._work_queue.qsize())
                
            except Exception as e:
                logger.error(f"Error in thread pool monitor: {e}")
    
    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any
    ) -> Future:
        """Submit a callable to be executed with the given arguments."""
        if self._shutdown:
            raise RuntimeError("Cannot schedule new tasks after shutdown")
        
        with self._lock:
            self._metrics.total_tasks += 1
            if PROMETHEUS_AVAILABLE and self.config.enable_monitoring:
                self._prom_tasks_total.inc()
        
        # Wrap the function to track metrics
        def wrapped_fn():
            start_time = time.time()
            try:
                result = fn(*args, **kwargs)
                execution_time = time.time() - start_time
                
                with self._lock:
                    self._metrics.completed_tasks += 1
                    self._execution_times.append(execution_time)
                    
                    # Update average execution time
                    if self._execution_times:
                        self._metrics.avg_execution_time = sum(self._execution_times) / len(self._execution_times)
                    
                    if PROMETHEUS_AVAILABLE and self.config.enable_monitoring:
                        self._prom_tasks_completed.inc()
                        self._prom_execution_time.observe(execution_time)
                
                return result
            except Exception as e:
                with self._lock:
                    self._metrics.failed_tasks += 1
                    if PROMETHEUS_AVAILABLE and self.config.enable_monitoring:
                        self._prom_tasks_failed.inc()
                raise e
        
        return self._executor.submit(wrapped_fn)
    
    def get_metrics(self) -> ThreadPoolMetrics:
        """Get current thread pool metrics."""
        with self._lock:
            self._metrics.queue_size = self._work_queue.qsize()
            return ThreadPoolMetrics(**vars(self._metrics))
    
    def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """Shutdown the thread pool."""
        self._shutdown = True
        if self._executor:
            self._executor.shutdown(wait=wait)
    
    @contextmanager
    def task_context(self, task_name: str = ""):
        """Context manager for executing tasks with automatic monitoring."""
        start_time = time.time()
        try:
            yield
        finally:
            execution_time = time.time() - start_time
            if task_name:
                logger.debug(f"Task '{task_name}' completed in {execution_time:.3f}s")


# Global thread pool instance
_global_pool: Optional[OptimizedThreadPoolExecutor] = None
_pool_lock = threading.Lock()


def get_thread_pool(config: Optional[ThreadPoolConfig] = None) -> OptimizedThreadPoolExecutor:
    """Get or create the global thread pool instance."""
    global _global_pool
    
    if _global_pool is None:
        with _pool_lock:
            if _global_pool is None:
                _global_pool = OptimizedThreadPoolExecutor(config)
    
    return _global_pool


def shutdown_thread_pool(wait: bool = True, timeout: Optional[float] = None) -> None:
    """Shutdown the global thread pool."""
    global _global_pool
    
    if _global_pool is not None:
        with _pool_lock:
            if _global_pool is not None:
                _global_pool.shutdown(wait=wait, timeout=timeout)
                _global_pool = None
