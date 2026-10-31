# 组件与场景

几何路径保存在组件 SVG 中，组合位置只保存在场景 JSON 中，避免重复维护坐标。

## 新组件

绘制带 `viewBox` 的 SVG，通常为 `0 0 400 400`。部件分别分组并命名。使用闭合路径、基础几何和必要的 clipPath/mask，不嵌入图片。填色采用 `assets/style.json` 的 HEX。需要点纹的形状加 `data-grain="1"`，组合脚本会叠加同形状的既定矢量点纹：

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">
  <g id="paper-pieces">
    <path id="first-piece" d="M80 110 L285 75 L320 290 L115 325 Z" fill="#709E5D" data-grain="1"/>
    <path id="second-piece" d="M100 250 L300 170 L330 340 L120 360 Z" fill="#B2D345" data-grain="1"/>
    <path id="overlap" d="M103 249 L300 170 L320 290 L115 325 Z" fill="#008638" data-grain="1"/>
  </g>
</svg>
```

这只是闭合色块与叠色的格式示例，不代表具体物品。源码与导出分开，工具不改写输入。

## 场景

```json
{
  "schema":"supermarket-scene/v1",
  "canvas":{"width":800,"height":400,"background":"transparent"},
  "items":[
    {"id":"milk","source":"catalog:milk","label":"牛奶","bbox":[0,0,400,400]},
    {"id":"yogurt","source":"yogurt.svg","label":"酸奶","bbox":[400,0,400,400]}
  ]
}
```

`source` 为 `catalog:<id>` 或相对场景的 SVG。`bbox` 是组合区域，等比居中适配而非拉伸。背景默认并应明确写为 `transparent`，独立 SVG/PNG 和组合总览都透明；复用旧场景时去掉历史底色。只有用户明确要求底色时才使用色板 token 或既定 HEX。用户需要额外颜色时用 `extraColors:{"token":"#RRGGBB"}` 声明，并记录用途。用户要求给已有组件改色时可用 `paletteOverrides:{"#旧色":"#新色"}`。

脚本可在任意目录运行，资源相对于脚本定位。`--list` 列出组件。输出目录必须尚不存在：

- `overview.svg`、`overview-transparent.svg`：分组总览，ID 已隔离。
- `overview.png`、`individual/`：实际渲染的总览与每个素材的透明 SVG/PNG。
- `scene.json`、`source-assets/`、`provenance.json`：可复查、可再次组合的输入。
- `assets.zip`：可交付素材包。

`--svg-only` 不导出 PNG。正常 PNG 路线只使用已有 Node/sharp，不安装依赖或联网；失败时保留输入和 SVG，修复后换新目录导出。

导入 Figma/Illustrator 等软件后需实际检查分组和点纹；只看预览不能证明目标应用的可编辑性。不要用改扩展名的方式伪造原生工程。
