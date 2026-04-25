#!/bin/bash
set -e

cd /app/
plantform="$(uname -m)"
PLANT_PATH=${PLANT_PATH:-/app/env}
plant="${PLANT_PATH}_${plantform}"
source /app/environment.sh
source "$plant/bin/activate"

# 启动 Xvfb（如果需要非 headless 模式）
if [ "$HEADLESS" != "true" ] || [ "$ENABLE_XVFB" = "true" ]; then
    echo "启动 Xvfb 虚拟 X Server..."
    export DISPLAY=${DISPLAY:-:99}
    DISPLAY_NUM="${DISPLAY#:}"
    DISPLAY_NUM="${DISPLAY_NUM%%.*}"
    rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}"

    nohup Xvfb "$DISPLAY" -screen 0 1920x1080x24 -ac >/tmp/xvfb.log 2>&1 &
    XVFB_PID=$!
    echo "Xvfb 已启动 (PID: $XVFB_PID, DISPLAY=$DISPLAY)"
    
    # 等待 Xvfb 启动
    sleep 2
    if ! kill -0 "$XVFB_PID" 2>/dev/null; then
        echo "Xvfb 启动失败，日志如下："
        cat /tmp/xvfb.log || true
        if [ "$HEADLESS" != "true" ]; then
            exit 1
        fi
    fi
fi

python3 main.py -job True -init True
