import streamlit as st
import requests
import json
import time
from ollama import Client
import urllib3
# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# ---------------------------
# CONFIG
# ---------------------------
VCENTER_URL = "https://vcenter.com/"
VCENTER_USER = "user_id"
VCENTER_PASS = "password"
SOURCE_VM = "vm_id"
CLUSTER = "cluster_id"
HOST = "host_id"
# Initialize Ollama client
ollama_client = Client(host="http://localhost:11434")
# ---------------------------
# VMWARE FUNCTIONS
# ---------------------------
def get_vmware_token():
   r = requests.post(
       f"{VCENTER_URL}/rest/com/vmware/cis/session",
       auth=(VCENTER_USER, VCENTER_PASS),
       verify=False
   )
   r.raise_for_status()
   return r.json()["value"]
def clone_vm(vm_name, token):
   url = f"{VCENTER_URL}/rest/vcenter/vm?action=clone"
   headers = {"Content-Type": "application/json", "vmware-api-session-id": token}
   data = {
       "spec": {
           "name": vm_name,
           "source": SOURCE_VM,
           "placement": {"cluster": CLUSTER, "host": HOST}
       }
   }
   r = requests.post(url, headers=headers, json=data, verify=False)
   r.raise_for_status()
   return r.json()["value"]
def patch_cpu(vm_id, cpu_count, token):
   url = f"{VCENTER_URL}/rest/vcenter/vm/{vm_id}/hardware/cpu"
   headers = {"Content-Type": "application/json", "vmware-api-session-id": token}
   data = {"spec": {"count": cpu_count, "cores_per_socket": 2}}
   r = requests.patch(url, headers=headers, json=data, verify=False)
   r.raise_for_status()
def patch_memory(vm_id, memory_mib, token):
   url = f"{VCENTER_URL}/rest/vcenter/vm/{vm_id}/hardware/memory"
   headers = {"Content-Type": "application/json", "vmware-api-session-id": token}
   data = {"spec": {"size_MiB": memory_mib}}
   r = requests.patch(url, headers=headers, json=data, verify=False)
   r.raise_for_status()
def power_on(vm_id, token):
   url = f"{VCENTER_URL}/rest/vcenter/vm/{vm_id}/power/start"
   headers = {"Content-Type": "application/json", "vmware-api-session-id": token}
   r = requests.post(url, headers=headers, json={}, verify=False)
   r.raise_for_status()
def deploy_vm_agent(vm_name, cpu, ram_gb):
   """Deploy VM with all specifications"""
   try:
       token = get_vmware_token()
       vm_id = clone_vm(vm_name, token)
       time.sleep(5)
       patch_cpu(vm_id, cpu, token)
       time.sleep(5)
       patch_memory(vm_id, ram_gb * 1024, token)
       time.sleep(5)
       power_on(vm_id, token)
       return True, f"VM '{vm_name}' has been deployed successfully with {cpu} CPU cores and {ram_gb} GB RAM!"
   except Exception as e:
       return False, f"Deployment failed: {str(e)}"
# ---------------------------
# AGENTIC AI FUNCTION
# ---------------------------
def chat_with_agent(user_input, conversation_history, current_step):
   """Main chatbot function that handles both normal chat and deployment flow"""
   system_prompt = f"""You are a friendly VM provisioning assistant.
   Current deployment step: {current_step}
   MODES:
   1. NORMAL CHAT: For general conversation, be helpful and friendly
   2. DEPLOYMENT FLOW: When user wants to deploy VM, follow this exact step-by-step:
      - Step 1: Ask for VM name only
      - Step 2: Ask for CPU cores only  
      - Step 3: Ask for RAM in GB only
      - Step 4: Confirm and deploy
   Always respond naturally based on the current step. Don't ask for multiple things at once.
   """
   messages = [
       {"role": "system", "content": system_prompt},
       *conversation_history,
       {"role": "user", "content": user_input}
   ]
   try:
       response = ollama_client.chat(model="llama3.1:8b", messages=messages)
       return response['message']['content']
   except Exception as e:
       return f"Sorry, I'm having trouble connecting. Error: {str(e)}"
# ---------------------------
# STREAMLIT UI
# ---------------------------
st.title("🤖 VM Deployment Agent")
# Initialize session state
if "chat_history" not in st.session_state:
   st.session_state.chat_history = []
if "deployment_step" not in st.session_state:
   st.session_state.deployment_step = "normal"  # normal, ask_name, ask_cpu, ask_ram, confirm
if "vm_details" not in st.session_state:
   st.session_state.vm_details = {"name": "", "cpu": 0, "ram": 0}
# Display chat history
for chat in st.session_state.chat_history:
   if chat["role"] == "user":
       st.chat_message("user").write(chat["content"])
   else:
       st.chat_message("assistant").write(chat["content"])
# User input
user_input = st.chat_input("Type your message here...")
if user_input:
   # Add user message to history
   st.session_state.chat_history.append({"role": "user", "content": user_input})
   st.chat_message("user").write(user_input)
   # Check if user wants to start deployment
   if st.session_state.deployment_step == "normal" and any(keyword in user_input.lower() for keyword in ["deploy", "create", "new vm", "provision"]):
       st.session_state.deployment_step = "ask_name"
       response = "Great! Let's deploy a new VM. What would you like to name your virtual machine?"
       st.session_state.chat_history.append({"role": "assistant", "content": response})
       st.chat_message("assistant").write(response)
   # Deployment flow - step by step
   elif st.session_state.deployment_step == "ask_name":
       # Store VM name and ask for CPU
       st.session_state.vm_details["name"] = user_input
       st.session_state.deployment_step = "ask_cpu"
       response = f"Perfect! VM name set to '{user_input}'. How many CPU cores would you like?"
       st.session_state.chat_history.append({"role": "assistant", "content": response})
       st.chat_message("assistant").write(response)
   elif st.session_state.deployment_step == "ask_cpu":
       # Try to extract CPU number
       try:
           cpu = int(''.join(filter(str.isdigit, user_input)))
           if cpu > 0:
               st.session_state.vm_details["cpu"] = cpu
               st.session_state.deployment_step = "ask_ram"
               response = f"Got it! {cpu} CPU cores. How much RAM in GB would you like?"
               st.session_state.chat_history.append({"role": "assistant", "content": response})
               st.chat_message("assistant").write(response)
           else:
               response = "Please enter a valid number of CPU cores (e.g., 2, 4, 8):"
               st.session_state.chat_history.append({"role": "assistant", "content": response})
               st.chat_message("assistant").write(response)
       except:
           response = "I didn't understand that. Please enter a number for CPU cores (e.g., 2, 4, 8):"
           st.session_state.chat_history.append({"role": "assistant", "content": response})
           st.chat_message("assistant").write(response)
   elif st.session_state.deployment_step == "ask_ram":
       # Try to extract RAM number
       try:
           ram = int(''.join(filter(str.isdigit, user_input)))
           if ram > 0:
               st.session_state.vm_details["ram"] = ram
               st.session_state.deployment_step = "confirm"
               # Get final confirmation using LLM for natural response
               confirm_prompt = f"User provided all VM details: Name: {st.session_state.vm_details['name']}, CPU: {st.session_state.vm_details['cpu']} cores, RAM: {st.session_state.vm_details['ram']} GB. Ask for confirmation to deploy in a friendly way."
               confirm_response = ollama_client.chat(
                   model="llama3.1:8b",
                   messages=[{"role": "user", "content": confirm_prompt}]
               )
               response = confirm_response['message']['content']
               st.session_state.chat_history.append({"role": "assistant", "content": response})
               st.chat_message("assistant").write(response)
           else:
               response = "Please enter a valid amount of RAM in GB (e.g., 4, 8, 16):"
               st.session_state.chat_history.append({"role": "assistant", "content": response})
               st.chat_message("assistant").write(response)
       except:
           response = "I didn't understand that. Please enter a number for RAM in GB (e.g., 4, 8, 16):"
           st.session_state.chat_history.append({"role": "assistant", "content": response})
           st.chat_message("assistant").write(response)
   elif st.session_state.deployment_step == "confirm":
       # Check if user confirms deployment
       if any(keyword in user_input.lower() for keyword in ["yes", "yep", "sure", "go ahead", "deploy", "confirm"]):
           # Deploy the VM
           with st.spinner("🚀 Deploying your VM..."):
               success, deploy_result = deploy_vm_agent(
                   st.session_state.vm_details["name"],
                   st.session_state.vm_details["cpu"],
                   st.session_state.vm_details["ram"]
               )
           # Generate final response using LLM
           result_prompt = f"VM deployment completed. Result: {deploy_result}. Provide a friendly summary to the user."
           final_response = ollama_client.chat(
               model="llama3.1:8b",
               messages=[{"role": "user", "content": result_prompt}]
           )
           response = final_response['message']['content']
           st.session_state.chat_history.append({"role": "assistant", "content": response})
           st.chat_message("assistant").write(response)
           # Reset deployment state
           st.session_state.deployment_step = "normal"
           st.session_state.vm_details = {"name": "", "cpu": 0, "ram": 0}
       else:
           # User cancelled or said no
           st.session_state.deployment_step = "normal"
           st.session_state.vm_details = {"name": "", "cpu": 0, "ram": 0}
           response = "Okay, deployment cancelled. How can I help you with something else?"
           st.session_state.chat_history.append({"role": "assistant", "content": response})
           st.chat_message("assistant").write(response)
   else:
       # Normal conversation
       with st.spinner("🤔 Thinking..."):
           response = chat_with_agent(user_input, st.session_state.chat_history, st.session_state.deployment_step)
       st.session_state.chat_history.append({"role": "assistant", "content": response})
       st.chat_message("assistant").write(response)
# Sidebar with current status
with st.sidebar:
   st.header("📋 Current Status")
   if st.session_state.deployment_step != "normal":
       st.write("**Deployment in Progress**")
       st.write(f"**Step:** {st.session_state.deployment_step.replace('_', ' ').title()}")
       st.write(f"**VM Name:** {st.session_state.vm_details['name'] or 'Not set'}")
       st.write(f"**CPU Cores:** {st.session_state.vm_details['cpu'] or 'Not set'}")
       st.write(f"**RAM (GB):** {st.session_state.vm_details['ram'] or 'Not set'}")
       if st.button("Cancel Deployment"):
           st.session_state.deployment_step = "normal"
           st.session_state.vm_details = {"name": "", "cpu": 0, "ram": 0}
           st.rerun()
   else:
       st.info("💡 Say 'deploy a VM' to start provisioning!")
   st.header("ℹ️ How it works")
   st.write("""
   1. **Normal chat**: Ask anything!
   2. **Start deployment**: Say "deploy a VM"
   3. **Provide details**: VM name → CPU → RAM
   4. **Confirm**: Say "yes" to deploy
   """)