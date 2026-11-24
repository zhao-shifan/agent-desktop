// 剥离 main/v1 分支里的人设内容（张子媛/GIRLFRIEND）——只用于 main/v1 同步，zzy 保留人设
const fs = require("fs");
for (const f of ["index.html", "小凡智能体-手机独立版.html"]) {
  let s = fs.readFileSync(f, "utf8");
  // 1) 人设常量块整体删除
  s = s.replace(/\/\* 小凡的女朋友：[\s\S]*?以后还要带她去好多好多地方 💗";\n/, "");
  s = s.replace(/const GIRLFRIEND_RULES =[\s\S]*?别说个没完。";\n/, "");
  s = s.replace(/const GIRLFRIEND_CARD =[\s\S]*?以后还要带她去好多好多地方 💗";\n/, "");
  // 2) persona 结尾引用 GIRLFRIEND_RULES → 换成中性收尾
  s = s.replace(/\+ GIRLFRIEND_RULES\};/g, '};');
  // 3) /girlfriend 指令块删除
  s = s.replace(/if\(cmd === "girlfriend"[\s\S]*?\n\s*\}\n/, "");
  // 4) help 表格里的女朋友行删除
  s = s.replace(/\| `\/girlfriend`[^\n]*\n/g, "");
  // 5) 其余提及张子媛/女朋友的行删除（人设相关散句）
  s = s.split("\n").filter(l => !/张子媛|女朋友/.test(l)).join("\n");
  fs.writeFileSync(f, s);
  const n = (s.match(/张子媛|GIRLFRIEND|girlfriend|女朋友/g) || []).length;
  console.log(f, "剩余人设引用:", n);
}
