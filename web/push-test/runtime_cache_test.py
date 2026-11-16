import unittest
from unittest.mock import patch
import signals
from live_test import message, LiveTests

class ParserCacheTests(unittest.TestCase):
    def test_equivalence_freshness_edits_and_copy_isolation(self):
        signals._parsed_content.cache_clear()
        now=1700000000
        rows=[message(1,now),message(2,now,rank='R1000+'),message(3,now,coin='xyz:ABC')]
        rows += [dict(rows[0],body=rows[0]['body']+'㍿'*5000),dict(rows[0],title='invalid')]
        for row in rows:
            for delta in (-31,-30,0,1800,1801):
                for age in (None,1800):
                    self.assertEqual(signals.parse_messages(row,now+delta,max_age=age),signals._parse_messages_uncached(row,now+delta,max_age=age))
        row=rows[0]
        cached=signals.parse_messages(row,now);cached[0]['oi']={'bad':True};cached[0]['value']='mutated'
        self.assertEqual(signals.parse_messages(row,now),signals._parse_messages_uncached(row,now))
        changed=dict(row,title=row['title'].replace('+0.39%','+0.99%'))
        self.assertEqual(signals.parse_messages(changed,now)[0]['value'],'+0.99%')
        before=signals._parsed_content.cache_info().hits
        signals.parse_messages(row,now+1)
        self.assertGreater(signals._parsed_content.cache_info().hits,before)
        for n in range(200):signals.parse_messages(message(n,now),now)
        self.assertLessEqual(signals._parsed_content.cache_info().currsize,128)

class PersistTests(LiveTests):
    def test_idle_tick_does_not_rewrite_and_pruning_does(self):
        self.tick([message(1,self.now)])
        with patch.object(self.app,'save',wraps=self.app.save) as save:
            self.tick([message(1,self.now)],self.now+1)
            self.assertEqual(save.call_count,0)
            self.tick([],self.now+1801)
            self.assertEqual(save.call_count,1)
