import tempfile
import unittest
from pathlib import Path

from scripts.review_java_file import summarize_file


SAMPLE_JAVA = """
public class SampleService {

    public void safeMethod() throws Exception {
        RLock lock = redissonClient.getLock("safe");
        boolean acquired = false;
        try {
            acquired = lock.tryLock(1, 1, TimeUnit.SECONDS);
            if (!acquired) {
                return;
            }
            validateRequest();
            buildContext();
            executeWorkflow();
        } finally {
            if (acquired) {
                lock.unlock();
            }
        }
    }

    public void unsafeMethod() throws Exception {
        RLock lock = redissonClient.getLock("unsafe");
        try {
            boolean acquired = lock.tryLock(1, 1, TimeUnit.SECONDS);
            if (acquired) {
                executeWorkflow();
            }
        } finally {
            lock.unlock();
        }
    }

    public void processData() {
        Object data = loadData();
        Object result = convert(data);
        validateRequest();
        buildContext();
        executeWorkflow();
        logResult(result);
    }
}
"""


class ReviewJavaFileTest(unittest.TestCase):

    def test_summarize_method_detects_unconditional_unlock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "SampleService.java"
            path.write_text(SAMPLE_JAVA, encoding="utf-8")

            summary = summarize_file(path, "unsafeMethod")

            self.assertEqual(1, summary.method_count)
            self.assertIn("lock may be released unconditionally after tryLock", summary.methods[0].risks)

    def test_summarize_file_lists_methods(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "SampleService.java"
            path.write_text(SAMPLE_JAVA, encoding="utf-8")

            summary = summarize_file(path)

            self.assertEqual(3, summary.method_count)
            self.assertEqual(["safeMethod", "unsafeMethod", "processData"], [method.name for method in summary.methods])

    def test_detects_unclear_naming_and_mixed_responsibilities(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "SampleService.java"
            path.write_text(SAMPLE_JAVA, encoding="utf-8")

            summary = summarize_file(path, "processData")

            self.assertEqual(1, summary.method_count)
            self.assertIn("method name is too generic to express a clear responsibility", summary.methods[0].risks)
            self.assertIn("local variable names are too generic to express business meaning", summary.methods[0].risks)
            self.assertIn("method likely violates single responsibility across multiple workflow stages", summary.methods[0].risks)


if __name__ == "__main__":
    unittest.main()
