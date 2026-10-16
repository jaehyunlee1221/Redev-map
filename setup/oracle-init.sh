#!/bin/bash
# 오라클 클라우드 VM 생성 시 "초기화 스크립트(cloud-init)"에 붙여넣기 → GitHub 수집기(self-hosted runner) 자동 등록
# TOKEN: 저장소 Settings → Actions → Runners → New self-hosted runner 화면의 --token 값 (1시간 유효)
TOKEN=여기에_토큰_붙여넣기
REPO=https://github.com/jaehyunlee1221/Redev-map

set -e
exec > /var/log/runner-setup.log 2>&1
apt-get update && apt-get install -y python3-venv python3-pip git curl jq
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab
id runner || useradd -m -s /bin/bash runner
mkdir -p /home/runner/actions-runner /home/runner/redev-raw && cd /home/runner/actions-runner
A=$(uname -m | sed 's/x86_64/x64/;s/aarch64/arm64/')
V=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | jq -r .tag_name | tr -d v)
curl -sL -o r.tgz "https://github.com/actions/runner/releases/download/v$V/actions-runner-linux-$A-$V.tar.gz"
tar xzf r.tgz && rm r.tgz && chown -R runner:runner /home/runner
./bin/installdependencies.sh
sudo -u runner ./config.sh --unattended --url "$REPO" --token "$TOKEN" --name oracle-seoul --labels korea --replace
./svc.sh install runner && ./svc.sh start
echo DONE
