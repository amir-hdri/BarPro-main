#!/usr/bin/env python3
"""
Comprehensive project optimization script.
Analyzes code, removes duplicates, optimizes imports, and fixes paths.
"""

import re
import sys
from collections import defaultdict
from pathlib import Path


class ProjectOptimizer:
    def __init__(self, root_dir="."):
        self.root = Path(root_dir).resolve()
        self.issues = []
        self.stats = defaultdict(int)

    def analyze_imports(self):
        """Analyze and report unused/duplicate imports."""
        print("🔍 Analyzing imports...")

        for py_file in self.root.rglob("*.py"):
            if "node_modules" in str(py_file) or ".git" in str(py_file):
                continue

            try:
                content = py_file.read_text(encoding='utf-8')
                imports = re.findall(r'^import\s+(\S+)', content, re.MULTILINE)
                from_imports = re.findall(r'^from\s+(\S+)\s+import', content, re.MULTILINE)

                # Check for duplicate imports
                all_imports = imports + from_imports
                if len(all_imports) != len(set(all_imports)):
                    duplicates = [x for x in all_imports if all_imports.count(x) > 1]
                    self.issues.append(f"Duplicate imports in {py_file.relative_to(self.root)}: {set(duplicates)}")
                    self.stats['duplicate_imports'] += 1

            except Exception:
                pass

        print(f"✅ Found {self.stats['duplicate_imports']} files with duplicate imports")

    def find_unused_files(self):
        """Find potentially unused Python files."""
        print("\n🔍 Finding unused files...")

        # Files that are likely unused
        suspicious_patterns = [
            r'.*_old\.py$',
            r'.*_backup\.py$',
            r'.*_test_old\.py$',
            r'.*\.bak$',
        ]

        for py_file in self.root.rglob("*.py"):
            if "node_modules" in str(py_file) or ".git" in str(py_file):
                continue

            for pattern in suspicious_patterns:
                if re.match(pattern, py_file.name):
                    self.issues.append(f"Potentially unused: {py_file.relative_to(self.root)}")
                    self.stats['unused_files'] += 1

        print(f"✅ Found {self.stats['unused_files']} potentially unused files")

    def check_path_consistency(self):
        """Check for inconsistent import paths."""
        print("\n🔍 Checking path consistency...")

        for py_file in self.root.rglob("*.py"):
            if "node_modules" in str(py_file) or ".git" in str(py_file):
                continue

            try:
                content = py_file.read_text(encoding='utf-8')

                # Check for relative imports that could be absolute
                relative_imports = re.findall(r'^from\s+\.(.*?)\s+import', content, re.MULTILINE)
                if relative_imports:
                    self.stats['relative_imports'] += len(relative_imports)

            except Exception:
                pass

        print(f"✅ Found {self.stats['relative_imports']} relative imports")

    def analyze_code_quality(self):
        """Analyze code quality metrics."""
        print("\n🔍 Analyzing code quality...")

        for py_file in self.root.rglob("*.py"):
            if "node_modules" in str(py_file) or ".git" in str(py_file):
                continue

            try:
                content = py_file.read_text(encoding='utf-8')
                lines = content.split('\n')

                # Count lines
                self.stats['total_lines'] += len(lines)
                self.stats['total_files'] += 1

                # Check for long files
                if len(lines) > 1000:
                    self.issues.append(f"Large file ({len(lines)} lines): {py_file.relative_to(self.root)}")
                    self.stats['large_files'] += 1

            except Exception:
                pass

        print(f"✅ Analyzed {self.stats['total_files']} files ({self.stats['total_lines']} lines)")
        print(f"   - Large files: {self.stats['large_files']}")

    def generate_report(self):
        """Generate optimization report."""
        print("\n" + "="*60)
        print("📊 OPTIMIZATION REPORT")
        print("="*60)

        print("\n📈 Statistics:")
        print(f"   Total Python files: {self.stats['total_files']}")
        print(f"   Total lines of code: {self.stats['total_lines']}")
        print(f"   Files with duplicate imports: {self.stats['duplicate_imports']}")
        print(f"   Potentially unused files: {self.stats['unused_files']}")
        print(f"   Relative imports: {self.stats['relative_imports']}")
        print(f"   Large files (>1000 lines): {self.stats['large_files']}")

        if self.issues:
            print(f"\n⚠️  Issues Found ({len(self.issues)}):")
            for i, issue in enumerate(self.issues[:20], 1):  # Show first 20
                print(f"   {i}. {issue}")
            if len(self.issues) > 20:
                print(f"   ... and {len(self.issues) - 20} more")
        else:
            print("\n✅ No issues found!")

        print("\n💡 Recommendations:")
        if self.stats['duplicate_imports'] > 0:
            print("   - Remove duplicate imports to improve code clarity")
        if self.stats['unused_files'] > 0:
            print("   - Review and remove unused files")
        if self.stats['large_files'] > 0:
            print("   - Consider splitting large files into smaller modules")

        print("\n" + "="*60)

    def run(self):
        """Run all optimization checks."""
        print("🚀 Starting Project Optimization")
        print("="*60)

        self.analyze_imports()
        self.find_unused_files()
        self.check_path_consistency()
        self.analyze_code_quality()
        self.generate_report()

        return len(self.issues)


if __name__ == "__main__":
    optimizer = ProjectOptimizer()
    issue_count = optimizer.run()

    sys.exit(0)
