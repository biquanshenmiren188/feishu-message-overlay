"""Editable notification templates; expand only known fields once per alarm round."""
import re

DEFAULT_LINES = (
    ('行情来源', '{{行情来源}}'),
    ('触发价格', '触发价格：{{触发价格}} USDT'),
    ('触发原因', '{{触发原因}}'),
    ('时间', '{{时间}}（北京时间）'),
)
DEFAULT_TEMPLATE = '\n'.join(line for _, line in DEFAULT_LINES)
FIELDS = {name for name, _ in DEFAULT_LINES} | {'备注', '币种', '触发条件'}
TOKEN = re.compile(r'\{\{([^{}]+)\}\}')


def validate_template(text):
    unknown = set(TOKEN.findall(text)) - FIELDS
    if unknown:
        raise ValueError('无法识别内容字段：' + '、'.join(sorted(unknown)))
    return text


def render_content(rule, values):
    default = DEFAULT_TEMPLATE + ('\n{{备注}}' if rule.get('note') else '')
    content = rule.get('alarmContent', '')
    if rule.get('alarmContentMode') == 'template':
        template = content or default
        present = set(TOKEN.findall(template))
        # Preserve the actual routing and price facts when editing/deleting template lines.
        missing = [line for name, line in DEFAULT_LINES if name not in present]
        if rule.get('note') and '备注' not in present:
            missing.append('{{备注}}')
        if missing:
            template += '\n\n' + '\n'.join(missing)
        return TOKEN.sub(lambda match: str(values.get(match[1], match[0])), template)
    body = TOKEN.sub(lambda match: str(values[match[1]]), default)
    return content + '\n\n' + body if content else body
