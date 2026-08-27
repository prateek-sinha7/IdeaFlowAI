#!/bin/bash
#
# Helper script to fetch and verify SonarScanner binary checksum
#
# Usage:
#   ./scripts/setup-sonarscanner-checksum.sh [VERSION]
#
# Example:
#   ./scripts/setup-sonarscanner-checksum.sh 8.0.1.6346
#
# This script:
#   1. Downloads the SonarScanner binary for the specified version
#   2. Computes the SHA256 checksum
#   3. Outputs the checksum for use in .github/workflows/ci.yml
#

set -euo pipefail

# Default to 8.0.1.6346 if not specified
SONAR_VERSION="${1:-8.0.1.6346}"
SONAR_BINARY="sonar-scanner-cli-${SONAR_VERSION}-linux-x64"
SONAR_ZIP="${SONAR_BINARY}.zip"
TEMP_DIR=$(mktemp -d)

echo "🔍 Fetching SonarScanner v${SONAR_VERSION}..."
curl -sSL -o "${TEMP_DIR}/${SONAR_ZIP}" \
  "https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/${SONAR_ZIP}"

echo "📊 Computing SHA256 checksum..."
CHECKSUM=$(sha256sum "${TEMP_DIR}/${SONAR_ZIP}" | awk '{print $1}')

echo ""
echo "✅ Checksum for SonarScanner v${SONAR_VERSION}:"
echo ""
echo "SONAR_VERSION=\"${SONAR_VERSION}\""
echo "SONAR_CHECKSUM=\"${CHECKSUM}\""
echo ""
echo "📝 Update .github/workflows/ci.yml with the values above:"
echo "   - Search for 'SONAR_VERSION=' in the 'Install SonarScanner' step"
echo "   - Replace the version and checksum"
echo "   - Uncomment the checksum verification line"
echo ""

# Cleanup
rm -rf "${TEMP_DIR}"

echo "✨ Done!"
