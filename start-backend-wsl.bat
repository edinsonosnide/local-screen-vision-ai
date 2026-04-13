@echo off
echo Starting backend via WSL (LiteRT-LM)...
wsl -d Ubuntu -- bash -c "source ~/local-screen-vision-ai/.venv/bin/activate && cd /mnt/c/Users/edins/OneDrive/Desktop/local-screen-vision-ai/backend && python main.py"
pause
