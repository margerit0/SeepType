param(
  [Parameter(Mandatory = $true)][string]$Renderer
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Renderer)) {
  throw '找不到预览包装工具。请用 -Renderer 指定 visualize 技能的 scripts/render.py；现有 index.html 仍可直接打开。'
}
python $Renderer (Join-Path $PSScriptRoot 'ime-candidates.html') (Join-Path $PSScriptRoot 'index.html') --title '英语学习输入法 · 设计原型' --force
if ($LASTEXITCODE -ne 0) { throw '预览生成失败' }
