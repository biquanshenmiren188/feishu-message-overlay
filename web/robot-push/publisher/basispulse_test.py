import unittest
from basispulse import normalize, retry_delay, NoRedirect

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
    def test_no_redirects(self):
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://other.test'))

if __name__=='__main__': unittest.main()
