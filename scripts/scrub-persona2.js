// 第二遍：按行块删除残留的人设常量与指令
const fs = require("fs");
for (const f of ["index.html", "小凡智能体-手机独立版.html"]) {
  let lines = fs.readFileSync(f, "utf8").split("\n");
  const out = [];
  let skip = 0;
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (skip > 0) { skip--; continue; }
    if (/^const GIRLFRIEND_RULES =/.test(l) || /^\/\* \/girlfriend 指令的卡片文案 \*\//.test(l) || /^const GIRLFRIEND_CARD =/.test(l)) {
      // 跳到以 💗"; 结尾的行（常量结束）
      let j = i;
      while (j < lines.length && !/💗";\s*$/.test(lines[j])) j++;
      if (j < lines.length) { i = j; continue; }
    }
    if (/if\(cmd === "girlfriend"/.test(l)) {
      // 跳到含 GIRLFRIEND_CARD); 的行，再跳过一行 }
      let j = i;
      while (j < lines.length && !/GIRLFRIEND_CARD\);/.test(lines[j])) j++;
      if (j < lines.length) { i = j + 1; continue; }
    }
    out.push(l);
  }
  fs.writeFileSync(f, out.join("\n"));
  const n = (out.join("\n").match(/张子媛|GIRLFRIEND|girlfriend|女朋友/g) || []).length;
  console.log(f, "剩余人设引用:", n);
}
