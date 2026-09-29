from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import asdict, dataclass
from typing import Iterable


MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_FILES = 2_000
SCANNABLE_SUFFIXES = {
    ".java",
    ".properties",
    ".xml",
    ".pom",
    ".gradle",
    ".kts",
    ".item",
    ".json",
    ".yml",
    ".yaml",
    ".config",
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    severity: str
    rule: str
    message: str
    recommendation: str
    snippet: str


@dataclass(frozen=True)
class AnalysisResult:
    findings: list[Finding]
    files_scanned: int
    skipped_files: list[str]
    changed_files: list[str]
    updated_archive: bytes | None


RULES: tuple[tuple[str, str, str, re.Pattern[str]], ...] = (
    (
        "JDK-REMOVED-JAXB",
        "Élevée",
        "JAXB n’est plus fourni par le JDK depuis Java 11. Vérifiez la dépendance JAXB déclarée par le projet Talend et sa compatibilité avec la version cible.",
        re.compile(r"\bjavax\.xml\.bind\b"),
    ),
    (
        "JDK-REMOVED-ACTIVATION",
        "Élevée",
        "Java Activation n’est plus fourni par le JDK. Vérifiez que la dépendance correspondante est explicitement disponible dans le runtime Talend.",
        re.compile(r"\bjavax\.activation\b"),
    ),
    (
        "JDK-INTERNAL-API",
        "Élevée",
        "Cette API interne n’est pas un contrat Java stable et peut être inaccessible avec Java 17. Remplacez-la par une API publique ou validez son usage avec l’éditeur Talend.",
        re.compile(r"\b(?:sun\.misc\.|jdk\.internal\.)"),
    ),
    (
        "NASHORN-REMOVED",
        "Élevée",
        "Nashorn a été retiré du JDK. Identifiez les scripts JavaScript concernés et choisissez un moteur pris en charge par votre distribution Talend.",
        re.compile(r"(?i)(?:getEngineByName\s*\(\s*[\"'](?:nashorn|javascript)[\"']|jdk\.nashorn|nashorn\.api)"),
    ),
    (
        "REFLECTION-ACCESS",
        "À vérifier",
        "Java 17 applique un encapsulage fort des modules. Testez cet accès réflexif sur le runtime cible et remplacez-le si possible par une API publique.",
        re.compile(r"\b(?:setAccessible\s*\(\s*true|trySetAccessible\s*\()"),
    ),
)

JAVA_TARGET_PATTERNS = (
    re.compile(
        r"(?i)(?P<prefix>\b(?:java\.version|maven\.compiler\.(?:source|target|release))\s*=\s*)(?P<version>1\.)?(?P<number>\d+)(?P<suffix>\s*(?:#.*)?)$"
    ),
    re.compile(
        r"(?i)(?P<prefix><(?:maven\.compiler\.(?:source|target|release)|maven\.compiler\.(?:source|target|release))>\s*)(?P<number>\d+)(?P<suffix>\s*</[^>]+>)"
    ),
    re.compile(
        r"(?i)(?P<prefix>\b(?:sourceCompatibility|targetCompatibility)\s*=\s*(?:JavaVersion\.VERSION_)?)(?P<number>\d+)(?P<suffix>\b.*)$"
    ),
    re.compile(
        r"(?i)(?P<prefix>\boptions\.release(?:\.set)?\s*\(?\s*)(?P<number>\d+)(?P<suffix>\s*\)?.*)$"
    ),
)

UPGRADE_PATTERNS = (
    re.compile(
        r"(?i)^(?P<prefix>\s*(?:java\.version|maven\.compiler\.(?:source|target|release))\s*=\s*)(?:1\.)?11(?P<suffix>\s*(?:#.*)?)$"
    ),
    re.compile(
        r"(?i)(?P<prefix><maven\.compiler\.(?:source|target|release)>\s*)11(?P<suffix>\s*</maven\.compiler\.(?:source|target|release)>)"
    ),
    re.compile(
        r"(?i)(?P<prefix>\b(?:sourceCompatibility|targetCompatibility)\s*=\s*(?:JavaVersion\.VERSION_)?)(?:1\.)?11(?P<suffix>\b.*)$"
    ),
    re.compile(
        r"(?i)(?P<prefix>\boptions\.release(?:\.set)?\s*\(?\s*)11(?P<suffix>\s*\)?.*)$"
    ),
)


def _iter_findings(path: str, text: str) -> Iterable[Finding]:
    for line_number, line in enumerate(text.splitlines(), start=1):
        for rule, severity, recommendation, pattern in RULES:
            if pattern.search(line):
                yield Finding(
                    path=path,
                    line=line_number,
                    severity=severity,
                    rule=rule,
                    message=f"Référence détectée : {rule}",
                    recommendation=recommendation,
                    snippet=line.strip()[:240],
                )

        for pattern in JAVA_TARGET_PATTERNS:
            match = pattern.search(line)
            if match and int(match.group("number")) < 17:
                yield Finding(
                    path=path,
                    line=line_number,
                    severity="Élevée",
                    rule="JAVA-TARGET-BELOW-17",
                    message=f"Cible Java inférieure à 17 ({match.group('number')}).",
                    recommendation="Passez cette configuration à Java 17, puis vérifiez la configuration effective du job dans Talend Studio.",
                    snippet=line.strip()[:240],
                )
                break


def _is_scannable(path: str) -> bool:
    lower_path = path.lower()
    return lower_path.endswith(".gradle.kts") or any(
        lower_path.endswith(suffix) for suffix in SCANNABLE_SUFFIXES
    )


def _upgrade_text(path: str, text: str) -> str:
    if not _is_scannable(path):
        return text

    updated_lines = []
    for line in text.splitlines(keepends=True):
        updated_line = line
        for pattern in UPGRADE_PATTERNS:
            updated_line, count = pattern.subn(
                lambda match: f"{match.group('prefix')}17{match.group('suffix')}",
                updated_line,
                count=1,
            )
            if count:
                break
        updated_lines.append(updated_line)
    return "".join(updated_lines)


def analyze_archive(archive_bytes: bytes, upgrade_java_target: bool = False) -> AnalysisResult:
    """Inspect a Talend export ZIP and optionally update explicit Java 11 targets."""
    try:
        source_archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except (zipfile.BadZipFile, OSError) as error:
        raise ValueError("Le fichier fourni n’est pas une archive ZIP valide.") from error

    findings: list[Finding] = []
    skipped_files: list[str] = []
    changed_files: list[str] = []
    replacements: dict[str, bytes] = {}
    files_scanned = 0

    with source_archive:
        for info in source_archive.infolist():
            if info.is_dir() or not _is_scannable(info.filename):
                continue
            if files_scanned >= MAX_FILES:
                skipped_files.append(f"Limite atteinte : {MAX_FILES} fichiers analysés")
                break
            if info.file_size > MAX_FILE_SIZE:
                skipped_files.append(info.filename)
                continue

            raw_content = source_archive.read(info)
            text = raw_content.decode("utf-8", errors="replace")
            files_scanned += 1
            findings.extend(_iter_findings(info.filename, text))

            if upgrade_java_target:
                updated_text = _upgrade_text(info.filename, text)
                if updated_text != text:
                    replacements[info.filename] = updated_text.encode("utf-8")
                    changed_files.append(info.filename)

        updated_archive = None
        if replacements:
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as destination:
                for info in source_archive.infolist():
                    data = replacements.get(info.filename)
                    if data is None:
                        data = source_archive.read(info)
                    destination.writestr(info, data)
            updated_archive = output.getvalue()

    return AnalysisResult(
        findings=findings,
        files_scanned=files_scanned,
        skipped_files=skipped_files,
        changed_files=changed_files,
        updated_archive=updated_archive,
    )


def findings_csv(findings: list[Finding]) -> bytes:
    output = io.StringIO(newline="")
    fieldnames = list(asdict(findings[0]).keys()) if findings else [
        "path",
        "line",
        "severity",
        "rule",
        "message",
        "recommendation",
        "snippet",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(asdict(finding) for finding in findings)
    return output.getvalue().encode("utf-8-sig")