export const DEFAULT_TEMPLATE = '{{行情来源}}\n触发价格：{{触发价格}} USDT\n{{触发原因}}\n{{时间}}（北京时间）';

export function contentDraft(rule) {
  const content = rule.alarmContent || '';
  const defaults = DEFAULT_TEMPLATE + (rule.note ? '\n{{备注}}' : '');
  if (rule.alarmContentMode === 'template') return content || defaults;
  // Existing custom text stays before the system details, exactly as before.
  return content ? content + '\n\n' + defaults : defaults;
}
