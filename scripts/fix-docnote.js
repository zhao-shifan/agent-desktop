// 修复 main 分支 DOC_NOTE 重复（v2，字符串匹配避免正则转义问题）
const fs = require("fs");
let lines = fs.readFileSync("index.html", "utf8").split("\n");
const idxs = [];
lines.forEach((l, i) => { if (l.includes("const DOC_NOTE")) idxs.push(i); });
console.log("找到 DOC_NOTE:", idxs.map(i => i + 1).join(","));
lines.splice(idxs[0], 1); // 删旧版（第一处）
const k = lines.findIndex(l => l.includes("const DOC_NOTE"));
const tail = "；5)【严格执行】用户明确指定了文档内容（如“只有文字你好”“就写一句话XX”）时，文件内容必须严格等于用户指定的内容，一个字都不许扩写，严禁自行添加摘要/正文/结论/建议等章节结构。\"};";
if (lines[k].includes("之类的废话。\"};")) {
  lines[k] = lines[k].replace("之类的废话。\"};", "之类的废话" + tail);
} else if (!lines[k].includes("严格执行")) {
  lines[k] = lines[k].replace(/\"\};$/, tail);
}
fs.writeFileSync("index.html", lines.join("\n"));
console.log("DOC_NOTE count:", (lines.join("\n").match(/const DOC_NOTE/g) || []).length);
console.log("rule5:", lines[k].includes("严格执行"));
