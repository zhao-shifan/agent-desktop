// MCP 市场 · 精选目录（本地内置，离线可用）
// 来源：官方 modelcontextprotocol/servers + awesome-mcp-servers 精选
// 结构：{name,label,desc,cat,command,args,note} 添加后可再在面板里改参数
window.MCP_CATALOG = [
  // 📁 文件与系统
  {name:"filesystem", label:"文件系统", cat:"文件", desc:"安全读写指定文件夹（最实用，推荐首选）", command:"npx", args:["-y","@modelcontextprotocol/server-filesystem","D:/"]},
  {name:"everything", label:"演示/测试", cat:"文件", desc:"官方演示服务器，验证 MCP 通不通", command:"npx", args:["-y","@modelcontextprotocol/server-everything"]},
  // 🌐 网络与搜索
  {name:"fetch", label:"网页抓取", cat:"网络", desc:"抓取网页正文转文本（需装 uv）", command:"uvx", args:["mcp-server-fetch"]},
  {name:"brave-search", label:"Brave 搜索", cat:"网络", desc:"网页搜索（需免费 Brave API Key）", command:"npx", args:["-y","@modelcontextprotocol/server-brave-search"], note:"需在 env 里填 BRAVE_API_KEY"},
  // 🧠 智能增强
  {name:"memory", label:"长期记忆", cat:"智能", desc:"跨对话知识图谱记忆", command:"npx", args:["-y","@modelcontextprotocol/server-memory"]},
  {name:"think", label:"深度思考", cat:"智能", desc:"复杂问题分步推理框架", command:"npx", args:["-y","@modelcontextprotocol/server-sequential-thinking"]},
  // 💼 办公效率
  {name:"word", label:"Word 文档", cat:"办公", desc:"创建/编辑/解析 .docx（第三方 office-word-mcp-server，需装 uv）", command:"uvx", args:["office-word-mcp-server"]},
  {name:"excel", label:"Excel 表格", cat:"办公", desc:"读写 .xlsx 数据、公式、多工作表", command:"npx", args:["-y","@negokaz/excel-mcp-server"]},
  {name:"gdrive", label:"Google 云盘", cat:"办公", desc:"搜索读取 Google Drive 文件（需 Google 凭据）", command:"npx", args:["-y","@modelcontextprotocol/server-gdrive"], note:"需要配置 Google OAuth 凭据"},
  {name:"slack", label:"Slack", cat:"办公", desc:"读写 Slack 消息频道（需 Slack Token）", command:"npx", args:["-y","@modelcontextprotocol/server-slack"], note:"需在 env 里填 SLACK_BOT_TOKEN"},
  {name:"puppeteer", label:"浏览器自动化", cat:"办公", desc:"控制无头浏览器：截图/点击/填表", command:"npx", args:["-y","@modelcontextprotocol/server-puppeteer"]},
  // 🎨 设计
  {name:"figma", label:"Figma 设计稿", cat:"设计", desc:"读取 Figma 设计稿数据转代码（Framelink，需 Figma API Key）", command:"npx", args:["-y","figma-developer-mcp","--stdio","--figma-api-key=你的KEY"], note:"把最后的「你的KEY」换成 Figma 个人访问令牌"},
  // 🛠 开发工具
  {name:"github-official", label:"GitHub", cat:"开发", desc:"仓库/Issue/PR 读写（需 GitHub Token）", command:"npx", args:["-y","@modelcontextprotocol/server-github"], note:"需在 env 里填 GITHUB_PERSONAL_ACCESS_TOKEN"},
  {name:"git", label:"Git 本地", cat:"开发", desc:"本地仓库 diff/commit/log 等操作（需装 uv）", command:"uvx", args:["mcp-server-git","--repository","D:/桌面版agent"]},
  {name:"sqlite", label:"SQLite 数据库", cat:"开发", desc:"查询分析本地 .db 数据库", command:"uvx", args:["mcp-server-sqlite","--db-path","D:/桌面版agent/agent_data/xiaofan.db"]},
  // 📊 数据
  {name:"postgres", label:"PostgreSQL", cat:"数据", desc:"只读查询 Postgres 数据库（需连接串）", command:"npx", args:["-y","@modelcontextprotocol/server-postgres","postgresql://localhost/mydb"], note:"最后参数改成你的连接串"},
  {name:"time", label:"时间时区", cat:"数据", desc:"查任意时区当前时间与换算（需装 uv）", command:"uvx", args:["mcp-server-time","--local-timezone","Asia/Shanghai"]},
];
