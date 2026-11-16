import unittest,time,tempfile,json
from pathlib import Path
from signals import parse_messages,desktop_rows
from desktop_rules import DesktopRules
class ClusterTests(unittest.TestCase):
 def test_mixed_windows_and_filtering(self):
  now=time.time();m=dict(id='b'*64,senderType='bot',title='强信号聚集｜TOKEN｜2 组同时 ACTIVE',sentAt=__import__('datetime').datetime.fromtimestamp(now,__import__('datetime').timezone.utc).isoformat(),body='R1｜FF｜买 GATE → 卖 ASTER\nV2收敛 · 180秒 · 净均 +0.54% · ACTIVE 18s\nR0｜SF｜买 BITGET → 卖 ASTER\nV2收敛 · 60秒 · 净均 +0.21% · ACTIVE 1s')
  rows=desktop_rows(m,now);self.assertEqual([r['value'] for r in rows],['+0.54%','+0.21%'])
  with tempfile.TemporaryDirectory() as d:
   rules=DesktopRules(d);rules.data['desktop']['rules']['hide']['excluded_ranks']=['R0']
   self.assertIsNone(rules.decision('desktop','test',rows,now,record=False))
   rules.data['desktop']['rules']['hide']['excluded_ranks']=['R0','R1']
   self.assertEqual(rules.decision('desktop','test',rows,now,record=False),'hide')
  broken=dict(m,body=m['body'].replace('净均 +0.21%','净均 未知'));self.assertEqual(parse_messages(broken,now),[])
if __name__=='__main__':unittest.main()
