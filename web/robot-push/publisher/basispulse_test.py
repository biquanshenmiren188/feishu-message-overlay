import unittest
from basispulse import normalize, retry_delay, NoRedirect, retain_removed

class MirrorTests(unittest.TestCase):
    def sample(self):
        return {'sampledAt':'2026-10-04T00:00:00Z','complete':True,'active':[{'id':'a','enteredAt':'2026-10-04T00:00:00Z','updatedAt':'2026-10-04T00:00:00Z','validUntil':'2026-10-04T00:01:00Z','details':{'legs':[{'rate':None,'volume':0,'private':'excluded'}]},'private':'excluded'}],'clientSecret':'excluded'}
    def test_no_credentials_or_unknown_fields_in_cache(self):
        value=normalize(self.sample())
        self.assertNotIn('clientSecret',value)
        self.assertNotIn('private',value['active'][0])
        self.assertEqual(value['active'][0]['details']['legs'][0],{'rate':None,'volume':0})
    def test_bad_shape_rejected(self):
        for value in ({}, {'complete':False,'active':{}}, {'complete':'true','active':[]}):
            with self.assertRaises(ValueError): normalize(value)
    def test_duplicate_rejected(self):
        value=self.sample();value['active']*=2
        with self.assertRaises(ValueError): normalize(value)
    def test_backoff_and_retry_after(self):
        self.assertEqual([retry_delay(n) for n in range(1,7)],[5,10,20,40,80,120])
        self.assertEqual(retry_delay(1,'180'),180)
        self.assertEqual(retry_delay(1,'n/a'),5)
        self.assertEqual(retry_delay(1,'Sun, 04 Oct 2026 00:01:00 GMT',1791072000),60)
    def test_null_timestamp_does_not_drop_valid_cards(self):
        value=self.sample()
        value['active'].append(dict(value['active'][0],id='bad',validUntil=None))
        result=normalize(value)
        self.assertEqual([c['id'] for c in result['active']],['a'])
        self.assertFalse(result['complete'])
        self.assertEqual(result['invalidCards'],1)
    def test_news_fields_are_preserved_without_unknown_data(self):
        value=self.sample()
        value['active'][0]['details']['newsWarnings']=[{'exchange':'okx','summary':'delisting','status':'postponed','private':'excluded'},None]
        warnings=normalize(value)['active'][0]['details']['newsWarnings']
        self.assertEqual(warnings,[{'exchange':'okx','summary':'delisting','status':'postponed'}])
    def test_no_redirects(self):
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://other.test'))

    def test_shared_history_survives_restart_and_expires_at_exactly_thirty_seconds(self):
        from datetime import datetime
        first=normalize(self.sample());start=datetime.fromisoformat(first['sampledAt'].replace('Z','+00:00')).timestamp()
        gone=dict(first,active=[],sampledAt='2026-10-04T00:00:05Z')
        saved=retain_removed(gone,first,start+7)
        self.assertEqual(saved['retained'][0]['expiredAt'],'2026-10-04T00:00:05+00:00')
        self.assertEqual(saved['retained'][0]['card'],first['active'][0])
        import json
        restarted=json.loads(json.dumps(saved))
        self.assertEqual(len(retain_removed(gone,restarted,start+34.999)['retained']),1)
        self.assertEqual(retain_removed(gone,restarted,start+35)['retained'],[])
        self.assertEqual(retain_removed(first,saved,start+8),saved)
        returned=dict(first,sampledAt='2026-10-04T00:00:10Z')
        self.assertEqual(retain_removed(returned,saved,start+10)['retained'],[])

    def test_partial_snapshot_keeps_known_card_without_inventing_failure(self):
        from datetime import datetime
        first=normalize(self.sample());start=datetime.fromisoformat(first['sampledAt'].replace('Z','+00:00')).timestamp()
        partial=dict(first,active=[],complete=False,sampledAt='2026-10-04T00:00:05Z')
        kept=retain_removed(partial,first,start+5)
        self.assertEqual(kept['active'],first['active']);self.assertEqual(kept['retained'],[])

if __name__=='__main__': unittest.main()
