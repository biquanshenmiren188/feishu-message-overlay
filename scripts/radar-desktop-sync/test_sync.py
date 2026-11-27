import hashlib
import io
import json
import unittest
from unittest.mock import patch

import sync


class ReleaseSyncTests(unittest.TestCase):
    def setUp(self):
        self.tag = "v2026.11.12.3"
        self.package = b"test package"
        self.asset = {
            "name": "FeishuMessageOverlay-win-x64.zip",
            "state": "uploaded",
            "digest": "sha256:" + hashlib.sha256(self.package).hexdigest(),
            "size": len(self.package),
        }
        self.release = dict(tag_name=self.tag, draft=False, prerelease=False, assets=[self.asset])
        self.commit = "b" * 40

    def fetch(self, current=None, data=None):
        self.asset["browser_download_url"] = (
            f"https://github.com/{sync.REPO}/releases/download/{self.tag}/{self.asset['name']}"
        )
        output = io.BytesIO()
        with patch.object(sync, "api", side_effect=[self.release, {"sha": self.commit}]), \
             patch.object(sync, "urlopen", return_value=io.BytesIO(self.package if data is None else data)) as download:
            sync.fetch(current, output)
        return output.getvalue(), download.call_count

    def test_both_package_names_and_repeat(self):
        for name in (self.asset["name"], f"FeishuMessageOverlay-{self.tag}-win-x64.zip"):
            with self.subTest(name=name):
                self.asset["name"] = name
                content, downloads = self.fetch()
                header, body = content.split(b"\n", 1)
                self.assertEqual((body, downloads), (self.package, 1))
                self.assertEqual(self.fetch(json.loads(header)), (b"", 0))
                changed = dict(json.loads(header), SourceCommit="0" * 40)
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.fetch(changed)

    def test_rejects_corruption_and_size_mismatches(self):
        for data in (self.package[:-1], self.package + b"!", b"x" * len(self.package)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.fetch(data=data)

    def test_rejects_ambiguous_packages_and_prereleases(self):
        self.release["prerelease"] = True
        with self.assertRaisesRegex(ValueError, "Official"):
            self.fetch()
        self.release["prerelease"] = False
        self.release["assets"].append(self.asset)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.fetch()

    def test_older_github_version_does_not_download(self):
        self.assertEqual(self.fetch({"Version": "v2026.11.13.1"}), (b"", 0))


if __name__ == "__main__":
    unittest.main()
