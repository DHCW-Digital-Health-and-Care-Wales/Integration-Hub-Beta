# --- Configuration ---

# Get all arguments passed to make.
# Filter out known targets to find 'extra' arguments.
KNOWN_TARGETS := all help install secrets build start send logs stop
EXTRA_ARGS    := $(filter-out $(KNOWN_TARGETS),$(MAKECMDGOALS))

# --- Phony Targets ---

# Declare targets that don't represent files.
.PHONY: $(KNOWN_TARGETS) $(EXTRA_ARGS)

# --- Main Targets ---

all: help

help:
	@echo "Usage: make [target] [arguments]"
	@echo ""
	@echo "Targets:"
	@echo "  install   Install Python dependencies (hl7)."
	@echo "  secrets   Force generation of the .secrets file."
	@echo "  build     Build (or rebuild) Docker containers (Usage: make build <profile>)"
	@echo "  start     Start Docker containers. (Usage: make run <profile>)"
	@echo "  send      Send a HL7 message. (Usage: make send <hl7-message-filename>)"
	@echo "  logs      Follow logs from services. (Usage: make logs <service_name>)"
	@echo "  stop      Stop all Docker containers."
	@echo ""
	@echo "Examples:"
	@echo "  make build phw-to-mpi"
	@echo "  make start phw-to-mpi"
	@echo "  make send test_message.hl7"
	@echo "  make logs mpi-hl7-mock-receiver"
	@echo "  make stop"

# --- Application Targets ---

## 🐍 install: Install Python dependencies
install:
	pip install hl7

## 🔒 secrets: Explicitly generate the .secrets file
# This target depends on the file .secrets.
# Running 'make secrets' will ensure the file is created.
secrets: .secrets
	@echo ".secrets file is present."

## ⚒️ build: (Re-)Build Docker containers for a profile
build:
	@echo "Building Docker Containers for Profile: $(EXTRA_ARGS)..."
	docker compose --profile $(EXTRA_ARGS) build

## ▶️ start: Start Docker containers
# This target 'depends' on the .secrets FILE.
# Make will check if .secrets exists.
# - If it exists, the dependency is met, and it runs the 'docker compose' command.
# - If it does NOT exist, Make will run the target that *creates* .secrets first.
start: .secrets
	@echo "Starting Docker Compose with profile: $(EXTRA_ARGS)..."
	docker compose --profile $(EXTRA_ARGS) up -d

## 🧪 send: Send a HL7 message
# Uses $(EXTRA_ARGS) as path to file containing hl7 message.
send:
	@echo "Sending HL7 file: $(EXTRA_ARGS)..."
	mllp_send --loose --file $(EXTRA_ARGS) --port 2575 127.0.0.1

## 📖 logs: Follow container logs
# Uses $(EXTRA_ARGS) to pass service names to the command.
logs:
	@echo "Following logs..."
	docker compose logs -f $(EXTRA_ARGS)

## ⏹️ stop: Stop all Docker containers
stop:
	@echo "Stopping Docker Compose..."
	docker compose --profile "*" down

# --- File Dependencies ---

# This is the 'real' target that creates the file.
# It is only run if the file '.secrets' does not exist.
.secrets:
	@echo "Generating new .secrets file..."
	python3 generate_secrets.py > .secrets


# --- Dummy Target ---

# Catche any "extra" argument and gives it an empty recipe, 
# so 'make' doesn't error.
$(EXTRA_ARGS):
	@# This is a dummy target to catch the extra args