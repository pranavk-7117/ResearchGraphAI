"""
Tests for Background Job Queue, Atomic Worker Locks, and Fault Isolation.
"""

import pytest
from app.database import SessionLocal
from app import models
from app.services.jobs import JobService


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_job_lifecycle_and_atomic_locking(db):
    prof_id = "test-jobs-user"
    prof = db.query(models.Profile).filter(models.Profile.id == prof_id).first()
    if not prof:
        prof = models.Profile(id=prof_id, email="jobs@test.com")
        db.add(prof)
        db.commit()

    proj = models.ResearchProject(user_id=prof_id, topic="Robotics")
    db.add(proj)
    db.commit()
    db.refresh(proj)

    # Create job
    job = JobService.create_job(db, job_type="discovery", project_id=proj.id)
    assert job.status == "pending"
    assert job.stage == "queued"
    assert job.progress == 0.0

    # Acquire job with worker lock
    worker_id = "test-worker-1"
    locked = JobService.acquire_next_job(db, worker_id=worker_id)
    assert locked is not None
    assert locked.id == job.id
    assert locked.status == "processing"
    assert locked.locked_by == worker_id

    # Second worker cannot acquire the same job (SKIP LOCKED)
    worker_2 = "test-worker-2"
    second_locked = JobService.acquire_next_job(db, worker_id=worker_2)
    assert second_locked is None

    # Cleanup
    db.delete(job)
    db.delete(proj)
    db.commit()
