# Ollama Setup Guide for Cold Email System

## Current Status
❌ Ollama server at `192.168.1.9:11434` is not accessible from this machine.

## Quick Diagnostics

Run these commands to troubleshoot:

```bash
# 1. Check if Ollama is running on the remote machine (192.168.1.9)
ssh user@192.168.1.9 "systemctl status ollama" # Linux
# OR
ssh user@192.168.1.9 "ps aux | grep ollama"    # Mac/Linux

# 2. Check if the port is accessible
nc -zv 192.168.1.9 11434
# OR
telnet 192.168.1.9 11434

# 3. Try curl from this machine
curl http://192.168.1.9:11434/api/tags

# 4. If using firewall, allow the port
# On remote machine (Linux):
sudo ufw allow 11434/tcp

# On remote machine (Mac):
# Check System Preferences > Security & Privacy > Firewall
```

## Option 1: Run Ollama Locally (Recommended for Testing)

```bash
# Install Ollama on your Mac
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model
ollama pull qwen2.5:7b

# Ollama will automatically start on localhost:11434

# Test it
python3 test_ollama_qwen.py http://localhost:11434
```

## Option 2: Configure Remote Ollama Server

On the machine at `192.168.1.9`:

```bash
# 1. Make sure Ollama is installed
which ollama

# 2. Configure Ollama to listen on all interfaces
# Edit /etc/systemd/system/ollama.service (Linux) or launchd config (Mac)
# Add: Environment="OLLAMA_HOST=0.0.0.0:11434"

# Linux (systemd):
sudo systemctl edit ollama
# Add:
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart ollama

# Mac (if using launchd or just running manually):
OLLAMA_HOST=0.0.0.0:11434 ollama serve

# 3. Pull the model if not already present
ollama pull qwen2.5:7b

# 4. Verify it's listening
netstat -an | grep 11434
# Should show: tcp  0  0  0.0.0.0:11434  *:*  LISTEN

# 5. Test from remote machine
curl http://192.168.1.9:11434/api/tags
```

## Option 3: SSH Tunnel (Quick Fix)

If you can't configure the remote server, use SSH tunnel:

```bash
# On your Mac, create tunnel
ssh -L 11434:localhost:11434 user@192.168.1.9 -N -f

# Now test with localhost
python3 test_ollama_qwen.py http://localhost:11434
```

## Once Ollama is Running

Test with the script:
```bash
# Default (192.168.1.9)
python3 test_ollama_qwen.py

# Custom URL
python3 test_ollama_qwen.py http://localhost:11434

# Custom model
python3 test_ollama_qwen.py http://localhost:11434 qwen2.5:14b
```

## Expected Output (When Working)

```
============================================================
Testing Ollama Qwen Email Generation
============================================================

1️⃣  Testing connection to http://localhost:11434...
   ✅ Ollama is running!
   Available models: ['qwen2.5:7b', 'llama3.1:8b']

2️⃣  Connecting to OpenAI-compatible endpoint...

3️⃣  Testing basic completion with qwen2.5:7b...
   ✅ Connection successful!
   Response: Hello from Ollama!

4️⃣  Generating email subject...
   Subject: engineering team

5️⃣  Generating full email body...
============================================================
GENERATED EMAIL:
============================================================
[Full email here]
```

## Next Steps

After Ollama is working, we'll integrate it into your email generator by:
1. Adding Ollama as a fallback provider in `email_generator.py`
2. Testing email quality vs Groq
3. Deploying to production if quality is acceptable

**What would you like to do?**
- [ ] Install Ollama locally on this Mac
- [ ] Configure the remote server at 192.168.1.9
- [ ] Use SSH tunnel as quick fix
- [ ] Something else?
