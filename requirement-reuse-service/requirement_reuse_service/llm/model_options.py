"""Conservative, documented model capabilities for compatible chat endpoints."""
import re


def qwen_model(model):
    return 'qwen' in model.lower()


def reasoning_effort_for(model, requested):
    if not requested:
        return None
    name = model.lower()
    if 'gpt-oss' in name:
        allowed = {'low', 'medium', 'high'}
    elif re.search(r'qwen3[.-]8', name):
        allowed = {'low', 'medium', 'xhigh'}
    else:
        # Never apply a global reasoning setting to a model of unknown support.
        return None
    if requested not in allowed:
        raise ValueError(f'Reasoning effort {requested!r} is unsupported for {model}; choose one of {sorted(allowed)}.')
    return requested


def answer_without_thinking(content):
    """Strip only a leading Qwen thinking segment, never JSON string values.

    Some templates put the opening marker in the assistant prefix, leaving only
    the closing marker in content. Unclosed thinking is not a final answer.
    """
    stripped = content.lstrip()
    if stripped.startswith(('{', '```')):
        return content, False
    if '</think>' in stripped:
        return stripped.split('</think>', 1)[1].lstrip(), True
    if stripped.startswith('<think>'):
        raise ValueError('Qwen returned an unclosed thinking segment; no final answer was accepted.')
    return content, False
