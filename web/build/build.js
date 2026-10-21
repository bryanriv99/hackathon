const fs = require("fs");
const path = require("path");
const sass = require("sass");

const SRC = path.join(__dirname, "template-src");
const NODE = path.join(__dirname, "node_modules");
const OUT = path.join(__dirname, "..", "static");

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });
}

const styleFiles = walk(SRC)
  .filter((f) => f.endsWith(".scss"))
  .filter((f) => !/(^|[\\/])(_main|_variables)\.scss$/.test(f))
  .filter((f) => !f.endsWith("-theme.scss"))
  .filter((f) => !f.includes(`${path.sep}auth${path.sep}`))
  .sort();

const themeFile = path.join(__dirname, "diablos-theme.scss");
const customFile = path.join(__dirname, "pitcheo.scss");

const bundle = [themeFile, path.join(SRC, "_main.scss"), ...styleFiles, customFile]
  .map((f) => fs.readFileSync(f, "utf8").replace(/@import url\(http:/g, "@import url(https:"))
  .join("\n");

const result = sass.compileString(bundle, {
  loadPaths: [SRC, NODE],
  quietDeps: true,
  silenceDeprecations: ["import", "global-builtin", "color-functions", "slash-div", "mixed-decls"],
  logger: sass.Logger.silent,
});

const copy = (from, to) => {
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.copyFileSync(from, to);
};

fs.mkdirSync(path.join(OUT, "css"), { recursive: true });
fs.writeFileSync(path.join(OUT, "css", "app.css"), result.css);

const vendorCss = [
  path.join(NODE, "bootstrap", "dist", "css", "bootstrap.css"),
  path.join(NODE, "font-awesome", "css", "font-awesome.css"),
]
  .map((f) => fs.readFileSync(f, "utf8"))
  .join("\n");
fs.writeFileSync(path.join(OUT, "css", "vendor.css"), vendorCss);

for (const font of fs.readdirSync(path.join(NODE, "font-awesome", "fonts"))) {
  copy(path.join(NODE, "font-awesome", "fonts", font), path.join(OUT, "fonts", font));
}

const vendorJs = [
  path.join(NODE, "jquery", "dist", "jquery.min.js"),
  path.join(NODE, "popper.js", "dist", "umd", "popper.min.js"),
  path.join(NODE, "bootstrap", "dist", "js", "bootstrap.min.js"),
  path.join(NODE, "metismenu", "dist", "metisMenu.min.js"),
]
  .map((f) => fs.readFileSync(f, "utf8"))
  .join("\n;\n");
fs.mkdirSync(path.join(OUT, "js"), { recursive: true });
fs.writeFileSync(path.join(OUT, "js", "vendor.js"), vendorJs);
copy(path.join(NODE, "plotly.js-dist-min", "plotly.min.js"), path.join(OUT, "js", "plotly.min.js"));

console.log(`app.css: ${result.css.length} bytes from ${styleFiles.length + 2} scss files`);
