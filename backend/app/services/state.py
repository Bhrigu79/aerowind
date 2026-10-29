from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Experiment, ExperimentEvent
from app.domain.types import ExperimentState
from datetime import datetime
from app.core.exceptions import AerowindError

class InvalidStateTransitionError(AerowindError):
    def __init__(self, current: str, target: str):
        super().__init__(f"Invalid state transition from {current} to {target}", "invalid_transition")

class ExperimentStateMachine:

    _valid_transitions = {
        ExperimentState.DRAFT: [ExperimentState.PLANNED, ExperimentState.CANCELLED],
        ExperimentState.PLANNED: [ExperimentState.READY, ExperimentState.CANCELLED],
        ExperimentState.READY: [ExperimentState.RUNNING, ExperimentState.CANCELLED],
        ExperimentState.RUNNING: [ExperimentState.MEASURING, ExperimentState.FAILED, ExperimentState.CANCELLED],
        ExperimentState.MEASURING: [ExperimentState.ANALYZING, ExperimentState.FAILED, ExperimentState.CANCELLED],
        ExperimentState.ANALYZING: [ExperimentState.COMPLETED, ExperimentState.FAILED, ExperimentState.CANCELLED],
        ExperimentState.COMPLETED: [],
        ExperimentState.FAILED: [],
        ExperimentState.CANCELLED: [],
    }

    @classmethod
    async def transition(cls, session: AsyncSession, experiment: Experiment, target_state: ExperimentState, message: str = "") -> Experiment:
        current_state = ExperimentState(experiment.status)

        if target_state not in cls._valid_transitions[current_state]:
            raise InvalidStateTransitionError(current_state.value, target_state.value)

        experiment.status = target_state.value

        if target_state == ExperimentState.RUNNING:
            experiment.started_at = datetime.utcnow()
        elif target_state in (ExperimentState.COMPLETED, ExperimentState.FAILED, ExperimentState.CANCELLED):
            experiment.completed_at = datetime.utcnow()

        # Log event
        event = ExperimentEvent(
            experiment_id=experiment.id,
            stage=target_state.value,
            event_type="STATE_TRANSITION",
            message=message or f"Transitioned to {target_state.value}",
        )
        session.add(event)

        return experiment
