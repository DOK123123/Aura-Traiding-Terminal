"""Evaluate the actual Actions conditions, not a second copy of the routing rules."""
import ast
import re
from pathlib import Path

import pytest

WORKFLOW=Path('.github/workflows/aura-active43.yml')


def expressions():
    lines=WORKFLOW.read_text().splitlines()
    job=None;steps=[]
    for i,line in enumerate(lines):
        if line=='    if: >-':
            tail=[]
            for part in lines[i+1:]:
                if not part.startswith('      '):break
                tail.append(part.strip())
            job=' '.join(tail)
        if line.startswith('        if: '):
            # Each operation step has exactly one fixed script command.
            command=next(part.strip()[5:] for part in lines[i+1:] if part.startswith('        run: '))
            steps.append((line.strip()[4:],command))
    assert job and len(steps)==4
    return job,steps


def matches(expression,context):
    # Small test-only expression interpreter: equality, AND, OR, string constants.
    expression=re.sub(r'\b(?:github\.event_name|inputs\.(?:operation|tick_policy)|vars\.AURA_ACTIVE43_BITGET_SCHEDULER_ENABLED)\b',
        lambda match:repr(context[match[0]]),expression)
    tree=ast.parse(expression.replace('&&',' and ').replace('||',' or '),mode='eval')
    def value(node):
        if isinstance(node,ast.Expression):return value(node.body)
        if isinstance(node,ast.Constant) and type(node.value) is str:return node.value
        if isinstance(node,ast.BoolOp):
            if isinstance(node.op,ast.And):return all(value(v) for v in node.values)
            if isinstance(node.op,ast.Or):return any(value(v) for v in node.values)
        if isinstance(node,ast.Compare) and len(node.ops)==1 and isinstance(node.ops[0],ast.Eq):
            return value(node.left)==value(node.comparators[0])
        raise AssertionError('Unsupported workflow expression: '+ast.dump(node))
    return value(tree)


def selected(event,operation,enabled,policy='off_only'):
    context={'github.event_name':event,'inputs.operation':operation,'inputs.tick_policy':policy,
        'vars.AURA_ACTIVE43_BITGET_SCHEDULER_ENABLED':enabled}
    job,steps=expressions()
    return [command for condition,command in steps if matches(condition,context)] if matches(job,context) else []


@pytest.mark.parametrize('enabled',['false','','true','TRUE'])
@pytest.mark.parametrize('operation,flag',[('initialize',' --initialize'),('diagnostics',' --diagnose'),('tick',' --verify-off-tick')])
def test_manual_operations_do_not_depend_on_periodic_schedule_variable(enabled,operation,flag):
    assert selected('workflow_dispatch',operation,enabled)==['python -m scripts.active43_scheduler'+flag]


@pytest.mark.parametrize('enabled',['false','','true'])
def test_manual_saved_mode_is_explicit_and_does_not_depend_on_schedule(enabled):
    assert selected('workflow_dispatch','tick',enabled,'saved_mode')==['python -m scripts.active43_scheduler']
    assert selected('workflow_dispatch','tick',enabled,'')==['python -m scripts.active43_scheduler --verify-off-tick']


@pytest.mark.parametrize('enabled',['false','','TRUE'])
def test_scheduled_tick_stays_disabled_without_exact_opt_in(enabled):
    assert selected('schedule','',enabled,'')==[]


def test_periodic_tick_requires_exact_opt_in_and_ignores_dispatch_policy():
    assert selected('schedule','','true','')==['python -m scripts.active43_scheduler']
    assert selected('push','tick','true')==[]
    assert selected('workflow_dispatch','INVALID','true')==[]


def test_workflow_defaults_serialization_permissions_and_token_are_preserved():
    text=WORKFLOW.read_text()
    assert 'default: diagnostics' in text and 'default: off_only' in text
    assert "cron: '2-59/5 * * * *'" in text
    assert 'group: aura-active43-bitget' in text and 'cancel-in-progress: false' in text
    assert 'contents: read' in text and 'persist-credentials: false' in text
    assert text.count('${{ secrets.AURA_ACTIVE43_BITGET_SCHEDULER_SECRET }}')==4
    assert 'INVALID_MANUAL_TICK_POLICY' in text
    assert 'auto42' not in text.lower() and '/control' not in text


@pytest.mark.parametrize('policy,success',[('off_only',True),('',True),('saved_mode',True),('INVALID',False)])
def test_actual_workflow_policy_validation_fails_closed(policy,success):
    import os,subprocess,sys
    text=WORKFLOW.read_text()
    program=text.split("          python - <<'PYTHON'\n",1)[1].split('          PYTHON',1)[0]
    program='\n'.join(line[10:] for line in program.splitlines())
    env={'PATH':os.environ.get('PATH',''),'EVENT_NAME':'workflow_dispatch','OPERATION':'tick',
        'TICK_POLICY':policy,'PERIODIC_SCHEDULE_ENABLED':'false'}
    result=subprocess.run([sys.executable,'-c',program],env=env,capture_output=True,text=True,timeout=10)
    assert (result.returncode==0)==success
    assert ('INVALID_MANUAL_TICK_POLICY' in result.stderr)==(not success)
