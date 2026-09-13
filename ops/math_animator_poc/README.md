# T15 Phase 0 Renderer PoC

该目录只验证固定可信场景能否在独立 Manim 镜像中渲染。它不接收用户参数，
不执行 LLM 生成代码，也不修改知微的主依赖或主 Dockerfile。

推荐使用精确镜像及 digest：

```text
manimcommunity/manim:v0.21.0
sha256:89ab433ce59134a4dcf351deb2511e067ab354393c0bb7d1859f3e8f0b2406a3
```

在仓库根目录创建一个临时输出目录，然后以默认禁网、只读根文件系统和资源限制运行：

```powershell
$output = Join-Path $env:TEMP 'zhiwei-t15-poc-output'
New-Item -ItemType Directory -Force -Path $output | Out-Null
docker run --rm `
  --network none `
  --read-only `
  --cap-drop ALL `
  --security-opt no-new-privileges:true `
  --cpus 1 `
  --memory 768m `
  --pids-limit 128 `
  --tmpfs /tmp:rw,noexec,nosuid,size=128m `
  --env XDG_CACHE_HOME=/tmp/cache `
  --env MPLCONFIGDIR=/tmp/matplotlib `
  --mount type=bind,src="$PWD/ops/math_animator_poc",dst=/input,readonly `
  --mount type=bind,src="$output",dst=/output `
  manimcommunity/manim:v0.21.0 `
  manim -ql --disable_caching --media_dir /output /input/secant_to_tangent.py SecantToTangent
```

注意：上述容器边界只用于可信模板 PoC。若未来执行模型生成的任意 Python，
仍需一次性 job sandbox、独立可写目录、更严格的 syscall policy 和逃逸测试。

## 最小候选镜像

官方镜像包含 TeX 和较多无关运行时，只适合功能对照。无 LaTeX 的 MVP 可构建：

```powershell
docker build -f ops/math_animator_poc/Dockerfile.renderer-poc `
  -t zhiwei-math-renderer:poc ops/math_animator_poc
```

该镜像采用双阶段构建，运行阶段仅保留 Manim、Cairo/Pango、字体和 OpenGL
运行库。Phase 0 仍不把它加入 `docker-compose.yml`。

## 加固后的 Trixie 候选镜像

Phase 0 后续安全收敛使用 Debian Trixie、显式系统安全升级、哈希锁定的 Python
依赖，并从最终运行时删除 pip/setuptools/wheel：

```powershell
docker build -f ops/math_animator_poc/Dockerfile.renderer-trixie `
  -t zhiwei-math-renderer:trixie-poc ops/math_animator_poc
```

重新生成锁文件时只构建不会进入最终镜像的 `lockgen` 阶段：

```powershell
docker build --target lockgen `
  -f ops/math_animator_poc/Dockerfile.renderer-trixie `
  -t zhiwei-math-renderer:lockgen ops/math_animator_poc

docker run --rm `
  --mount type=bind,src="$PWD/ops/math_animator_poc",dst=/work `
  zhiwei-math-renderer:lockgen `
  --generate-hashes --resolver=backtracking --strip-extras `
  --output-file=/work/requirements-renderer.lock `
  /work/requirements-renderer.txt
```

最终候选镜像 digest 为
`sha256:e0c8c2909a56756b6ef8ea05138cfa1cea1fea6db5d176e8ff58715959532635`。
对应 CycloneDX 清单为 `renderer-trixie.sbom.cdx.json`。剩余 zlib High 的处置状态见
`CVE-2026-85091-risk-note.md`；在项目所有者签字前不能视为已接受。

## 学生对照验证

`student_validation/` 提供匿名 CSV 模板、交叉实验协议和自动门禁分析器。原始学生
响应只能保存在被忽略的 `artifacts/` 目录，不得提交真实身份或原始学习材料。
