import io
import unittest
import zipfile

from migration_engine import analyze_archive, findings_csv


def make_archive(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


class AnalyzeArchiveTests(unittest.TestCase):
    def test_detects_removed_jdk_api_and_old_java_target(self) -> None:
        archive = make_archive(
            {
                "jobs/Job.java": "import javax.xml.bind.JAXBContext;\n",
                "pom.xml": "<maven.compiler.release>11</maven.compiler.release>\n",
            }
        )

        result = analyze_archive(archive)

        self.assertEqual(result.files_scanned, 2)
        self.assertEqual(
            {finding.rule for finding in result.findings},
            {"JDK-REMOVED-JAXB", "JAVA-TARGET-BELOW-17"},
        )

    def test_updates_explicit_java_11_target_without_rewriting_java_source(self) -> None:
        archive = make_archive(
            {
                "pom.xml": "<maven.compiler.release>11</maven.compiler.release>\n",
                "jobs/Job.java": "class Job { int javaVersion = 11; }\n",
            }
        )

        result = analyze_archive(archive, upgrade_java_target=True)

        self.assertEqual(result.changed_files, ["pom.xml"])
        self.assertIsNotNone(result.updated_archive)
        with zipfile.ZipFile(io.BytesIO(result.updated_archive)) as updated:
            self.assertIn(b">17<", updated.read("pom.xml"))
            self.assertIn(b"javaVersion = 11", updated.read("jobs/Job.java"))

    def test_invalid_zip_returns_actionable_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "ZIP valide"):
            analyze_archive(b"not a zip")

    def test_csv_has_headers_when_no_findings(self) -> None:
        csv_content = findings_csv([]).decode("utf-8-sig")
        self.assertIn("path,line,severity,rule", csv_content)


if __name__ == "__main__":
    unittest.main()