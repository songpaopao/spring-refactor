import tempfile
import unittest
from pathlib import Path

from scripts.review_git_diff import summarize_diff_text


UNSAFE_DIFF = """diff --git a/TaskServiceImpl.java b/TaskServiceImpl.java
index 1111111..2222222 100644
--- a/TaskServiceImpl.java
+++ b/TaskServiceImpl.java
@@ -10,0 +11,8 @@
+    private void receivePoints() {
+        RLock lock = redissonClient.getLock(key);
+        try {
+            boolean acquired = lock.tryLock(3, 10, TimeUnit.SECONDS);
+        } finally {
+            lock.unlock();
+        }
+    }
"""


SIGNATURE_DIFF = """diff --git a/TaskController.java b/TaskController.java
index 1111111..2222222 100644
--- a/TaskController.java
+++ b/TaskController.java
@@ -20,1 +20,1 @@
-    public Result receive(Long taskId) {
+    public Result receive(Long taskId, String platform) {
"""


class ReviewGitDiffTest(unittest.TestCase):

    def test_detects_unconditional_unlock_risk(self):
        summary = summarize_diff_text(UNSAFE_DIFF)

        self.assertEqual(1, summary.file_count)
        self.assertIn("cleanup may be unconditional after tryLock in added code", summary.files[0].risks)

    def test_detects_public_signature_change(self):
        summary = summarize_diff_text(SIGNATURE_DIFF)

        self.assertEqual(1, summary.file_count)
        self.assertIn("public or protected method signature changed", summary.files[0].risks)


if __name__ == "__main__":
    unittest.main()
