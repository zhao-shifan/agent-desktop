const fs = require("fs");
const html = fs.readFileSync("D:\\桌面版agent\\index.html", "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
console.log("inline scripts:", scripts.length);
let bad = 0;
scripts.forEach((s, i) => {
  try { new Function(s); } catch (e) { bad++; console.log("SYNTAX ERROR in script #" + (i+1) + ":", e.message); }
});
console.log(bad === 0 ? "ALL PASS" : "HAS ERRORS");
