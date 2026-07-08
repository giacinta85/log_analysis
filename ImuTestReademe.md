# IMU Test README

本文件记录 RK3588 IMU 测试从部署到运行、下载日志、生成 RPY 图像的完整流程。

## 默认环境

- 3588 SSH：`lumosbot@192.168.54.110`
- 远端工程：`/home/lumosbot/thomas_ws/lumos_controller`
- 本地工具目录：`/Users/giacinta/workspace/lumos_ws/lumos_tools/log_analysis`
- 本地日志目录：`/Users/giacinta/workspace/lumos_ws/logs/imu`
- 本地图像目录：`/Users/giacinta/workspace/lumos_ws/lumos_tools/log_analysis/outputs`
- 双 IMU 测试程序：`build/example/daisi_imu_handler_test`
- 单 IMU 测试程序：`build/example/imu_handler_test`
- 测试采样频率：目标 `200Hz`，源码使用 `sleep_until` 固定 `5ms` 周期

当前 3588 串口映射：

```text
/dev/ttyUSB_imu  -> ttyUSB1
/dev/ttyUSB_imu2 -> ttyUSB0
/dev/ttyUSB1     -> 双 IMU 测试中的 imu_a
/dev/ttyUSB0     -> 双 IMU 测试中的 imu_b
```

## 文件说明

```text
log_analysis/
├── deploy_imu_env.sh                 # 部署映射规则，并上传 resource/ 下的测试源码
├── run_imu_test.sh                   # 一键运行 IMU 测试、下载日志、生成图
├── run.sh                            # log_analysis 通用入口，也可单独画 IMU 图
├── scripts/plot_imu_rpy.py           # 支持双 IMU 和单 IMU RPY 画图
└── resource/
    └── example/device-test/
        ├── daisi_imu_handler_test.cpp
        └── imu_handler_test.cpp
```

`resource/` 里的相对路径会按远端工程根目录同步。例如：

```text
resource/example/device-test/daisi_imu_handler_test.cpp
-> /home/lumosbot/thomas_ws/lumos_controller/example/device-test/daisi_imu_handler_test.cpp
```

双 IMU 和单 IMU 测试源码都放在 `resource/example/device-test/` 下。旧的 `source/` 目录仅作为历史副本保留，部署脚本默认使用 `resource/`。

## 1. 部署前检查

只检查 3588 当前映射、规则文件、是否有 IMU 测试进程，不修改远端：

```bash
cd /Users/giacinta/workspace/lumos_ws/lumos_tools/log_analysis
./deploy_imu_env.sh --check
```

期望看到：

```text
/dev/serial/by-path/platform-fc8c0000.usb-usb-0:1:1.0-port0 -> ../../ttyUSB1
/dev/serial/by-path/platform-xhci-hcd.6.auto-usb-0:1:1.0-port0 -> ../../ttyUSB0
/dev/ttyUSB_imu -> ttyUSB1
/dev/ttyUSB_imu2 -> ttyUSB0
```

## 2. 部署映射和源码

正式部署：

```bash
cd /Users/giacinta/workspace/lumos_ws/lumos_tools/log_analysis
./deploy_imu_env.sh
```

脚本会执行：

1. 检查是否有 IMU 测试进程正在运行。
2. 安装 udev 规则到远端：`/etc/udev/rules.d/99-lumos-imu.rules`。
3. reload udev，并验证 `/dev/ttyUSB_imu`、`/dev/ttyUSB_imu2`。
4. 上传 `resource/` 下的源码到远端 `lumos_controller` 工程。
5. 自动编译远端 `daisi_imu_handler_test` 和 `imu_handler_test`。

如果提示有 IMU 测试进程正在运行，先等当前测试结束，或手动确认后停止，再重新部署。

## 3. 手动设置 3588 串口映射

如果不使用 `deploy_imu_env.sh`，可以在 3588 上手动安装 udev 规则。不要在 IMU 测试正在运行时修改映射，先确认没有测试进程占用：

```bash
ssh 192.168.54.110
pgrep -af 'lumos_main|daisi_imu_handler_test|imu_handler_test|timeout .*imu' || true
```

先确认当前 USB 物理路径和 ttyUSB 的对应关系：

```bash
ls -l /dev/serial/by-path/* 2>/dev/null
udevadm info -q property -n /dev/ttyUSB0 | grep '^ID_PATH='
udevadm info -q property -n /dev/ttyUSB1 | grep '^ID_PATH='
```

当前期望映射是：

```text
platform-fc8c0000.usb-usb-0:1:1.0-port0   -> ttyUSB1 -> /dev/ttyUSB_imu
platform-xhci-hcd.6.auto-usb-0:1:1.0-port0 -> ttyUSB0 -> /dev/ttyUSB_imu2
```

写入 udev 规则：

```bash
sudo tee /etc/udev/rules.d/99-lumos-imu.rules >/dev/null <<'EOF'
# Lumos daisi IMU stable serial aliases.
SUBSYSTEM=="tty", ENV{ID_PATH}=="platform-fc8c0000.usb-usb-0:1:1.0-port0", SYMLINK+="ttyUSB_imu", GROUP="dialout", MODE="0666"
SUBSYSTEM=="tty", ENV{ID_PATH}=="platform-xhci-hcd.6.auto-usb-0:1:1.0-port0", SYMLINK+="ttyUSB_imu2", GROUP="dialout", MODE="0666"
EOF
```

重新加载规则并触发 tty 设备：

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
sleep 1
```

验证软链接：

```bash
ls -l /dev/ttyUSB_imu /dev/ttyUSB_imu2
readlink -f /dev/ttyUSB_imu
readlink -f /dev/ttyUSB_imu2
```

期望结果：

```text
/dev/ttyUSB_imu  -> /dev/ttyUSB1
/dev/ttyUSB_imu2 -> /dev/ttyUSB0
```

如果某台 3588 的 `ID_PATH` 和上面不一致，以 `udevadm info` 查到的实际 `ID_PATH` 为准，只替换规则里的 `ENV{ID_PATH}=="..."`，不要改 `SYMLINK+="ttyUSB_imu"` 和 `SYMLINK+="ttyUSB_imu2"` 的含义。

## 4. 编译远端测试程序

`deploy_imu_env.sh` 已经会自动编译。需要手动重新编译时，在 3588 上执行：

```bash
ssh 192.168.54.110
cd /home/lumosbot/thomas_ws/lumos_controller/build
make daisi_imu_handler_test imu_handler_test -j$(nproc)
```

编译完成后确认文件存在：

```bash
ls -lh example/daisi_imu_handler_test example/imu_handler_test
```

## 5. 运行双 IMU 测试

默认运行双 IMU 测试，时长 10 分钟：

```bash
cd /Users/giacinta/workspace/lumos_ws/lumos_tools/log_analysis
./run_imu_test.sh
```

等价于：

```bash
./run_imu_test.sh --imu both -t 10
```

脚本会执行完整流程：

1. SSH 到 3588。
2. 如果发现旧的 `lumos_main`、`daisi_imu_handler_test`、`imu_handler_test` 或 `timeout .*imu` 占用，会先停止再启动新测试。
3. 检查串口映射。
4. 后台启动测试程序并断开 SSH。
5. 本地用进度条等待测试结束。
6. 回连 3588 检查日志和 `DONE code=124`。
7. 下载日志到本地 `logs/imu`。
8. 自动生成 RPY 图到 `outputs/`。

`DONE code=124` 是正常结果，表示 `timeout` 到时退出。

## 6. 单独运行 ttyUSB0 或 ttyUSB1 测试

只测试 `/dev/ttyUSB0`：

```bash
cd /Users/giacinta/workspace/lumos_ws/lumos_tools/log_analysis
./run_imu_test.sh --imu ttyUSB0
```

只测试 `/dev/ttyUSB1`：

```bash
./run_imu_test.sh --imu ttyUSB1
```

可指定时长，例如 1 分钟 smoke test：

```bash
./run_imu_test.sh --imu ttyUSB0 -t 1
./run_imu_test.sh --imu ttyUSB1 -t 1
```

`-t` 的单位是分钟，例如 `-t 10` 表示测试 10 分钟。不指定时默认 10 分钟。长参数 `--duration-minutes 10` 也仍然可用。注意：时长必须大于 0，不能传 `0`。

单 IMU 日志前缀为：

```text
ttyUSB0_drift_YYYYMMDD_HHMMSS_10min.log
ttyUSB1_drift_YYYYMMDD_HHMMSS_10min.log
```

脚本会自动生成单 IMU RPY 图。

注意：单 IMU 测试依赖远端 `imu_handler_test` 支持命令行设备参数。若远端仍是旧版硬编码 `/dev/ttyUSB0` 的二进制，需要先部署并重新编译 `resource/example/device-test/imu_handler_test.cpp`，否则 `--imu ttyUSB1` 可能仍读到 `/dev/ttyUSB0`。

注意：双 IMU 和单 IMU 测试程序的目标采样频率都是 `200Hz`。如果日志统计出来不是约 `200Hz`，优先确认远端二进制是否已经重新编译。

## 7. 手动用已有日志生成图

如果已有日志，只想重新画图：

```bash
cd /Users/giacinta/workspace/lumos_ws/lumos_tools/log_analysis
zsh ./run.sh -m imu -log <log_file_name>
```

也可以用一键测试脚本直接从已有日志生成图，不会连接 3588：

```bash
./run_imu_test.sh -log <log_file_name_or_rpy_stem>
./run_imu_test.sh -log <log_file_name_or_rpy_stem> --html
```

`-log` 可以传 `.log` 文件名、完整路径，或已经生成图像的 `_rpy` stem，例如：

```bash
./run_imu_test.sh -log daisi_imu_drift_20260708_170343_10min_rpy --html
```

示例：

```bash
zsh ./run.sh -m imu -log daisi_imu_drift_20260707_153749_10min.log
zsh ./run.sh -m imu -log ttyUSB0_drift_20260707_153749_10min.log
zsh ./run.sh -m imu -log ttyUSB1_drift_20260707_153749_10min.log
```

`run.sh` 会自动查找：

```text
当前目录
log_analysis/
/Users/giacinta/workspace/lumos_ws/logs/imu/
```

默认输出文件：

```text
log_analysis/outputs/<log_stem>_rpy.png
```

如需同时生成可交互 HTML，运行时增加 `--html`：

```bash
./run_imu_test.sh --html
zsh ./run.sh -m imu -log <log_file_name> --html
```

HTML 输出路径：

```text
log_analysis/outputs/<log_stem>_rpy.html
```

其中 PNG 是静态图；HTML 是可交互图。打开 HTML 后：

- HTML 会展示 `roll/pitch/yaw`、`omega_x/omega_y/omega_z`、`acc_x/acc_y/acc_z` 面板，用同一坐标系叠加对比 IMU A/B。
- 鼠标移动到曲线附近会显示当前 IMU、时间、R/P/Y 坐标、角速度 `omega` 和加速度 `acc`。
- 左键拖拽框选可以同时放大时间轴和纵坐标。
- 鼠标滚轮默认缩放当前图的纵坐标。
- 按住 `Shift` 滚轮缩放时间轴。
- 右键拖拽或 `Option/Alt` + 左键拖拽可以平移。
- 双击图像或点 `Reset` 恢复全量范围。

数据来源说明：

- `omega` 和 `acc` 来自测试程序中的 `handler.readQuatOmegaAcc(sample.quat, sample.omega, sample.acc)`，是从 IMU handler 直接读取的字段。
- `rpy` 不是直接从日志中的欧拉角原始字段读取，而是测试程序把四元数 `quat` 通过 `quaternionToEulerAngles(q)` 计算得到后写入日志。
- `rpy_delta_a_minus_b`、`relative_rpy_drift_from_start`、`omega_delta_a_minus_b`、`acc_delta_a_minus_b` 是测试程序对两块 IMU 的结果做差或相对初始值计算得到的派生量。

## 8. 常用命令汇总

部署检查：

```bash
./deploy_imu_env.sh --check
```

正式部署：

```bash
./deploy_imu_env.sh
```

远端编译：

```bash
ssh 192.168.54.110
cd /home/lumosbot/thomas_ws/lumos_controller/build
make daisi_imu_handler_test imu_handler_test -j$(nproc)
```

双 IMU 默认 10 分钟测试：

```bash
./run_imu_test.sh
```

单独 ttyUSB0 默认 10 分钟测试：

```bash
./run_imu_test.sh --imu ttyUSB0
```

单独 ttyUSB1 默认 10 分钟测试：

```bash
./run_imu_test.sh --imu ttyUSB1
```

单独 ttyUSB0/ttyUSB1 1 分钟测试：

```bash
./run_imu_test.sh --imu ttyUSB0 -t 1
./run_imu_test.sh --imu ttyUSB1 -t 1
```

指定 10 分钟测试：

```bash
./run_imu_test.sh -t 10
./run_imu_test.sh --imu ttyUSB0 -t 10
./run_imu_test.sh --imu ttyUSB1 -t 10
```

跳过画图：

```bash
./run_imu_test.sh --no-plot
./run_imu_test.sh --imu ttyUSB0 --no-plot
./run_imu_test.sh --imu ttyUSB1 --no-plot
```

手动画图：

```bash
zsh ./run.sh -m imu -log <log_file_name>
```

## 9. 输出位置

日志：

```text
/Users/giacinta/workspace/lumos_ws/logs/imu/
```

图像：

```text
/Users/giacinta/workspace/lumos_ws/lumos_tools/log_analysis/outputs/
```

## 10. 常见问题

### 没有继续画图

检查是否传了 `--no-plot`。如果没有，脚本应该自动画图。

单 IMU `ttyUSB0` 和 `ttyUSB1` 日志也已支持画图，格式为日志中的：

```text
rpy: <roll> <pitch> <yaw>
```

双 IMU 日志支持：

```text
imu_a rpy: <roll> <pitch> <yaw>
imu_b rpy: <roll> <pitch> <yaw>
```

### SSH 被沙箱拦截

在 Codex 环境中执行 SSH/SCP 时，可能需要批准网络访问。批准后重试同一命令。

### 串口被占用

`run_imu_test.sh` 会自动停止旧的 IMU 测试进程和 `lumos_main` 后再启动测试。如果不希望自动停止，请先手动检查：

```bash
ssh 192.168.54.110
pgrep -af 'lumos_main|daisi_imu_handler_test|imu_handler_test|timeout .*imu' || true
```

### 日志里没有 RPY

如果日志只有超时或没有 `rpy:` 行，画图脚本无法生成有效图像。先确认远端测试程序能读到 IMU 数据：

```bash
ssh 192.168.54.110
ls -l /dev/ttyUSB_imu /dev/ttyUSB_imu2 /dev/ttyUSB0 /dev/ttyUSB1 /dev/serial/by-path/* 2>/dev/null
```

### conda 环境问题

`run.sh` 会自动使用或创建 `lumos_log` 环境。如果环境损坏，可重建：

```bash
cd /Users/giacinta/workspace/lumos_ws/lumos_tools/log_analysis
zsh ./run.sh --rebuild
```
