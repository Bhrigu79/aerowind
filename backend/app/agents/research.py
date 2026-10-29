import json
from typing import Dict, Any
from app.gateway.gateway import ModelGateway
from app.schemas.research import HypothesisSchema, ExperimentPlanSchema, PlannerStrategySchema
from app.db.models import Project

class BaseAgent:
    def __init__(self, gateway: ModelGateway):
        self.gateway = gateway

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        from app.schemas.gateway import GatewayRequest, Message, MessageRole, TaskType
        full_system = f"{system_prompt}\n\nYou MUST respond with strictly valid JSON matching the requested schema."

        req = GatewayRequest(
            task_type=TaskType.REASONING,
            messages=[
                Message(role=MessageRole.SYSTEM, content=full_system),
                Message(role=MessageRole.USER, content=user_prompt)
            ],
            temperature=0.2
        )

        response = await self.gateway.complete(req)
        return response.content

class PlannerAgent(BaseAgent):
    async def analyze_project(self, project: Project, memory_summary: dict, progress: dict) -> dict:
        system = "You are the AEROWIND Planner Agent. Analyze the project objective, constraint progress, and research memory. Determine the next area of focus and explicitly state your reasoning."
        schema = PlannerStrategySchema.model_json_schema()
        user = f"Objective: {project.objective}\nProgress: {json.dumps(progress)}\nMemory: {json.dumps(memory_summary)}\nSchema: {json.dumps(schema)}\n\nGenerate the next strategy."
        raw = await self._call_llm(system, user)
        if raw.startswith("```json"):
            raw = raw[7:-3]
        elif raw.startswith("```"):
            raw = raw[3:-3]
        return json.loads(raw)

class HypothesisAgent(BaseAgent):
    async def generate_hypothesis(self, project: Project, focus_area: str, memory: str = "") -> HypothesisSchema:
        system = "You are the AEROWIND Hypothesis Agent. Propose a testable hypothesis based on the focus area. Consider the research memory provided."
        schema = HypothesisSchema.model_json_schema()
        user = f"Focus Area: {focus_area}\nMemory:\n{memory}\n\nSchema: {json.dumps(schema)}\n\nGenerate a hypothesis."
        raw = await self._call_llm(system, user)
        if raw.startswith("```json"):
            raw = raw[7:-3]
        elif raw.startswith("```"):
            raw = raw[3:-3]
        return HypothesisSchema.model_validate_json(raw)

class ExperimentDesignerAgent(BaseAgent):
    async def design_experiment(self, hypothesis: HypothesisSchema, target_system: str, baseline_config: dict = None) -> ExperimentPlanSchema:
        system = "You are the AEROWIND Experiment Designer Agent. Design a concrete experiment plan to test the given hypothesis. You MUST output a full candidate_configuration. Ensure that the selected independent variable changes from the baseline, but do not change unrelated dimensions."
        schema = ExperimentPlanSchema.model_json_schema()
        user = f"Hypothesis: {hypothesis.model_dump_json()}\nTarget System: {target_system}\nBaseline Config: {json.dumps(baseline_config)}\nSchema: {json.dumps(schema)}\n\nDesign the experiment."
        raw = await self._call_llm(system, user)
        if raw.startswith("```json"):
            raw = raw[7:-3]
        elif raw.startswith("```"):
            raw = raw[3:-3]
        return ExperimentPlanSchema.model_validate_json(raw)

class ResearcherAgent(BaseAgent):
    async def analyze_results(self, hypothesis: str, baseline_metrics: dict, candidate_metrics: dict, passed: bool) -> str:
        system = "You are the AEROWIND Researcher Agent. Analyze the experimental metrics and constraints."
        user = f"Hypothesis: {hypothesis}\nBaseline: {baseline_metrics}\nCandidate: {candidate_metrics}\nConstraints Passed: {passed}\n\nProvide a brief scientific conclusion (max 2 sentences)."
        raw = await self._call_llm(system, user)
        return raw.strip()
