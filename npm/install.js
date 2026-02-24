const os = require("os");
const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const VERSION = require("./package.json").version;
const platform = os.platform();   // "darwin", "linux", "win32"
const arch = os.arch();           // "arm64", "x64"

// Map platform/arch to GitHub release asset name
const assetMap = {
  "darwin-arm64": "ctrace-darwin-arm64",
  "darwin-x64":   "ctrace-darwin-x64",
  "linux-x64":    "ctrace-linux-x64",
};

const asset = assetMap[`${platform}-${arch}`];
if (!asset) {
  console.warn(`Warning: No pre-built binary for ${platform}-${arch}. Install Python and run: pip install clawtracerx`);
  process.exit(0);
}

const url = `https://github.com/kys42/clawtracerx/releases/download/v${VERSION}/${asset}`;
const destDir = path.join(__dirname, "binary");
fs.mkdirSync(destDir, { recursive: true });
const dest = path.join(destDir, "ctrace");

console.log(`Downloading ctrace ${VERSION} for ${platform}-${arch}...`);
try {
  execSync(`curl -fsSL -o "${dest}" "${url}"`, { stdio: "inherit" });
  fs.chmodSync(dest, 0o755);
  console.log("ctrace installed successfully.");
} catch (e) {
  console.warn(`Warning: Failed to download binary from ${url}`);
  console.warn("Install Python and run: pip install clawtracerx");
}
