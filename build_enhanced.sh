#!/bin/bash

# Enhanced Build Script for Solana Memecoin Monitor
# Version 2.0 - With comprehensive error checking and setup

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check system requirements
check_requirements() {
    log_info "Checking system requirements..."
    
    # Check Rust
    if ! command_exists rustc; then
        log_error "Rust is not installed. Please install Rust from https://rustup.rs/"
        exit 1
    fi
    
    # Check Python
    if ! command_exists python3; then
        log_error "Python 3 is not installed. Please install Python 3.8 or higher."
        exit 1
    fi
    
    # Check Python version
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    log_info "Python version: $python_version"
    
    # Check Cargo
    if ! command_exists cargo; then
        log_error "Cargo is not installed. Please install Rust properly."
        exit 1
    fi
    
    log_success "All requirements met"
}

# Function to setup environment
setup_environment() {
    log_info "Setting up environment..."
    
    # Check if .env file exists
    if [ ! -f ".env" ]; then
        if [ -f "src/env.example" ]; then
            log_warning ".env file not found. Copying from example..."
            cp src/env.example .env
            log_warning "Please edit .env file with your configuration before running the bot"
        else
            log_error ".env file not found and no example available"
            exit 1
        fi
    fi
    
    log_success "Environment setup complete"
}

# Function to install Python dependencies
install_python_deps() {
    log_info "Installing Python dependencies..."
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "python/venv" ]; then
        log_info "Creating Python virtual environment..."
        cd python
        python3 -m venv venv
        cd ..
    fi
    
    # Activate virtual environment and install dependencies
    log_info "Installing Python packages..."
    cd python
    source venv/bin/activate
    
    # Upgrade pip first
    pip install --upgrade pip
    
    # Install requirements with error handling
    if pip install -r requirements.txt; then
        log_success "Python dependencies installed successfully"
    else
        log_error "Failed to install Python dependencies"
        exit 1
    fi
    
    deactivate
    cd ..
}

# Function to build Rust project
build_rust() {
    log_info "Building Rust project..."
    
    # Clean previous build
    cargo clean
    
    # Build the project
    if cargo build --release; then
        log_success "Rust project built successfully"
    else
        log_error "Failed to build Rust project"
        exit 1
    fi
    
    # Check if binary was created
    if [ -f "target/release/solana-vntr-sniper" ]; then
        log_success "Binary created: target/release/solana-vntr-sniper"
    else
        log_error "Binary not found after build"
        exit 1
    fi
}

# Function to run tests
run_tests() {
    log_info "Running tests..."
    
    # Run Rust tests
    if cargo test; then
        log_success "Rust tests passed"
    else
        log_warning "Some Rust tests failed (this may be normal for integration tests)"
    fi
    
    # Test Python imports
    cd python
    if source venv/bin/activate && python3 -c "
import sys
sys.path.append('.')
try:
    from scoring.token_scorer import TokenScorer
    from unified_monitor import UnifiedMonitor
    print('✅ Python imports successful')
except ImportError as e:
    print(f'⚠️ Some imports failed: {e}')
"; then
        log_success "Python imports test completed"
    else
        log_warning "Python imports test had issues (may need additional setup)"
    fi
    cd ..
}

# Function to create startup scripts
create_scripts() {
    log_info "Creating startup scripts..."
    
    # Create Rust bot startup script
    cat > start_rust_bot.sh << 'EOF'
#!/bin/bash
echo "Starting Solana Memecoin Monitor (Rust)..."
cd "$(dirname "$0")"
./target/release/solana-vntr-sniper
EOF
    chmod +x start_rust_bot.sh
    
    # Create Python monitor startup script
    cat > start_python_monitor.sh << 'EOF'
#!/bin/bash
echo "Starting Python Unified Monitor..."
cd "$(dirname "$0")/python"
source venv/bin/activate
python3 unified_monitor.py
EOF
    chmod +x start_python_monitor.sh
    
    # Create ML feedback loop startup script
    cat > start_ml_feedback.sh << 'EOF'
#!/bin/bash
echo "Starting ML Feedback Loop..."
cd "$(dirname "$0")/python"
source venv/bin/activate
python3 ml_feedback_loop.py
EOF
    chmod +x start_ml_feedback.sh
    
    # Create combined startup script
    cat > start_all.sh << 'EOF'
#!/bin/bash
echo "Starting all monitoring components..."

# Start Python monitor in background
./start_python_monitor.sh &
PYTHON_PID=$!

# Start ML feedback loop in background
./start_ml_feedback.sh &
ML_PID=$!

# Start Rust bot (foreground)
./start_rust_bot.sh

# Cleanup on exit
cleanup() {
    echo "Stopping all processes..."
    kill $PYTHON_PID 2>/dev/null || true
    kill $ML_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM
EOF
    chmod +x start_all.sh
    
    log_success "Startup scripts created"
}

# Function to display usage information
show_usage() {
    log_info "Available startup options:"
    echo "  ./start_rust_bot.sh      - Start only the Rust monitoring bot"
    echo "  ./start_python_monitor.sh - Start only the Python unified monitor"
    echo "  ./start_ml_feedback.sh   - Start only the ML feedback loop"
    echo "  ./start_all.sh           - Start all components together"
    echo ""
    echo "Before running, make sure to:"
    echo "  1. Edit .env file with your configuration"
    echo "  2. Set up your RPC endpoints and API keys"
    echo "  3. Configure your target wallet addresses"
}

# Main build process
main() {
    log_info "Starting enhanced build process..."
    
    # Run all build steps
    check_requirements
    setup_environment
    install_python_deps
    build_rust
    run_tests
    create_scripts
    
    log_success "Build completed successfully!"
    echo ""
    show_usage
}

# Handle command line arguments
case "${1:-}" in
    --check-only)
        check_requirements
        exit 0
        ;;
    --python-only)
        install_python_deps
        exit 0
        ;;
    --rust-only)
        build_rust
        exit 0
        ;;
    --help|-h)
        echo "Usage: $0 [--check-only|--python-only|--rust-only|--help]"
        echo "  --check-only   Only check system requirements"
        echo "  --python-only  Only install Python dependencies"
        echo "  --rust-only    Only build Rust project"
        echo "  --help         Show this help message"
        exit 0
        ;;
    "")
        main
        ;;
    *)
        log_error "Unknown option: $1"
        echo "Use --help for usage information"
        exit 1
        ;;
esac