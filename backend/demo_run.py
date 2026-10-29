import asyncio
import os
import sys
import json
import re
import uuid

# Ensure backend and tests are in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from app.main import app
from app.gateway.gateway import get_gateway
from app.schemas.gateway import GatewayResponse, Provider, TokenUsage

class DemoMockGateway:
    def __init__(self):
        self.target_dim = "temperature"

    async def initialize(self): pass
    async def shutdown(self): pass
    async def complete(self, request):
        sys_prompt = request.messages[0].content if request.messages else ""
        user_prompt = request.messages[1].content if len(request.messages) > 1 else ""

        if "Planner Agent" in sys_prompt:
            return GatewayResponse(
                content=json.dumps({"focus_area": "quality", "reason": "Reduce quality gap"}),
                raw_response={}, provider=Provider.OPENAI, model='mock',
                usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
                latency_ms=100.0, request_id=str(uuid.uuid4())
            )

        if "Hypothesis" in sys_prompt:
            m = re.search(r"optimizing the dimension: '([^']+)'", user_prompt)
            if m:
                self.target_dim = m.group(1)

            return GatewayResponse(
                content=json.dumps({
                    "claim": "Hypothesis 1",
                    "expected_effect": "Improve quality",
                    "target_metric": "quality_score",
                    "expected_direction": "increase",
                    "expected_magnitude": 5.0,
                    "confidence": 0.9,
                    "independent_variable": self.target_dim,
                    "control_description": "none",
                    "candidate_description": "Candidate 1",
                    "risks": "none",
                }),
                raw_response={}, provider=Provider.OPENAI, model='mock',
                usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
                latency_ms=100.0, request_id=str(uuid.uuid4())
            )

        if "Experiment Designer" in sys_prompt:
            cfg = {"temperature": 0.7}
            if self.target_dim == "chain_of_thought":
                cfg["chain_of_thought"] = True
            elif self.target_dim == "retrieval_enabled":
                cfg["retrieval_enabled"] = True
            elif self.target_dim == "few_shot_count":
                cfg["few_shot_count"] = 5
            elif self.target_dim == "temperature":
                cfg["temperature"] = 0.5
            else:
                cfg[self.target_dim] = "mock_value"

            return GatewayResponse(
                content=json.dumps({
                    "hypothesis_summary": "summary",
                    "candidate_configuration": cfg,
                    "changed_variables": [self.target_dim],
                    "held_constant_variables": [],
                    "workload": "web",
                    "metrics_to_measure": ["quality_score", "p95_latency_ms"],
                    "sample_size": 10,
                    "stop_conditions": ["none"],
                    "expected_result": "better"
                }),
                raw_response={}, provider=Provider.OPENAI, model='mock',
                usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
                latency_ms=100.0, request_id=str(uuid.uuid4())
            )

        if "Researcher Agent" in sys_prompt:
            return GatewayResponse(
                content="Results look reasonable.",
                raw_response={}, provider=Provider.OPENAI, model='mock',
                usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
                latency_ms=100.0, request_id=str(uuid.uuid4())
            )

        return GatewayResponse(
            content="{}",
            raw_response={}, provider=Provider.OPENAI, model='mock',
            usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
            latency_ms=100.0, request_id=str(uuid.uuid4())
        )

    def get_status(self): pass

app.dependency_overrides[get_gateway] = lambda: DemoMockGateway()
client = TestClient(app)

print('Creating project...')
res = client.post('/api/v1/projects/', json={
    'name': 'Happy Path Demo',
    'objective': 'Make it awesome',
    'target_system_description': 'Test agent',
    'constraints': [
        {'metric': 'quality_score', 'operator': '>=', 'value': 90},
        {'metric': 'p95_latency_ms', 'operator': '<=', 'value': 2000}
    ]
})
project = res.json()
pid = project['id']
print('Project ID:', pid)

res = client.post(f'/api/v1/research/sessions/{pid}', json={'max_iterations': 5, 'max_experiments': 10})
session = res.json()
sid = session['session_id']

for i in range(3):
    print(f'Running iteration {i+1}...')
    res = client.post(f'/api/v1/research/sessions/{sid}/iterate?runner_type=synthetic')
    print(f'Iteration {i+1} result:', res.json())

res = client.get(f'/api/v1/research/projects/{pid}/graph')
graph = res.json()

print('\n--- UI OBSERVATIONS ---')
for node in graph['nodes']:
    if node['type'] == 'experiment':
        print('\n[Experiment Card]')
        print('Title:', node['data']['title'])
        print('Hypothesis:', node['data']['hypothesis'])
        print('What Changed:', node['data'].get('what_changed'))
        print('Provenance:', node['data'].get('runner_type'))
        print('Decision:', node['data'].get('decision'))
        print('Strategy Reason:', node['data'].get('strategy_reason', {}).get('reason'))
        print('Metrics:', node['data'].get('candidate_metrics'))

print('\n[Current Best Card]')
print('Best Exp ID:', graph['current_best'])
print('Best Config:', graph['current_best_config'])
print('Current Gaps:', graph['current_gaps'])
