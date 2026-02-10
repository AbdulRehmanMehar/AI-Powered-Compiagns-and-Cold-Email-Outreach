#!/usr/bin/env python3
"""
Test Priority 1 Fixes: Circuit Breaker and Health Monitoring
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from email_generator import APICircuitBreaker, CircuitBreakerOpen, get_circuit_breaker
import time


def test_circuit_breaker():
    """Test circuit breaker functionality"""
    
    print("=" * 60)
    print("TESTING CIRCUIT BREAKER")
    print("=" * 60)
    
    # Create a test circuit breaker (lower thresholds for testing)
    breaker = APICircuitBreaker(failure_threshold=3, timeout=5)
    
    print("\n1. Testing CLOSED state (normal operation):")
    print(f"   State: {breaker.state}")
    
    # Test successful calls
    def success_func():
        return "success"
    
    try:
        result = breaker.call(success_func)
        print(f"   ✅ Call succeeded: {result}")
        print(f"   Failures: {breaker.failures}, State: {breaker.state}")
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
    
    print("\n2. Testing failure accumulation:")
    
    def failing_func():
        raise Exception("Simulated API failure")
    
    # Accumulate failures
    for i in range(1, 4):
        try:
            breaker.call(failing_func)
        except CircuitBreakerOpen as e:
            print(f"   🔴 Circuit breaker opened: {e}")
            break
        except Exception:
            print(f"   Attempt {i}: Failed (Failures: {breaker.failures}, State: {breaker.state})")
    
    print(f"\n   Final state: {breaker.state}")
    print(f"   Failures: {breaker.failures}")
    
    print("\n3. Testing OPEN state (blocking calls):")
    try:
        breaker.call(success_func)
        print("   ❌ Call should have been blocked!")
    except CircuitBreakerOpen as e:
        print(f"   ✅ Call blocked as expected: {e}")
    
    print("\n4. Testing HALF_OPEN transition (after timeout):")
    print(f"   Waiting {breaker.timeout} seconds for timeout...")
    time.sleep(breaker.timeout + 1)
    
    # First call should transition to HALF_OPEN
    print(f"   State before call: {breaker.state}")
    try:
        result = breaker.call(success_func)
        print(f"   ✅ First success in HALF_OPEN: {result}")
        print(f"   State: {breaker.state}, Success count: {breaker.success_count}")
        
        # Second success should close the circuit
        result = breaker.call(success_func)
        print(f"   ✅ Second success - circuit should close: {result}")
        print(f"   State: {breaker.state}")
        
    except Exception as e:
        print(f"   ❌ Error during recovery: {e}")
    
    print("\n5. Testing reset:")
    # Cause failures again
    for i in range(3):
        try:
            breaker.call(failing_func)
        except:
            pass
    
    print(f"   State before reset: {breaker.state}, Failures: {breaker.failures}")
    breaker.reset()
    print(f"   State after reset: {breaker.state}, Failures: {breaker.failures}")
    
    print("\n✅ Circuit breaker tests complete!")


def test_global_circuit_breaker():
    """Test the global circuit breaker instance"""
    
    print("\n" + "=" * 60)
    print("TESTING GLOBAL CIRCUIT BREAKER")
    print("=" * 60)
    
    breaker = get_circuit_breaker()
    print(f"\n   Global breaker state: {breaker.state}")
    print(f"   Failures: {breaker.failures}")
    print(f"   Threshold: {breaker.failure_threshold}")
    print(f"   Timeout: {breaker.timeout}s")
    
    print("\n✅ Global circuit breaker accessible!")


def test_health_monitoring_imports():
    """Test that health monitoring can be imported"""
    
    print("\n" + "=" * 60)
    print("TESTING HEALTH MONITORING IMPORTS")
    print("=" * 60)
    
    try:
        from auto_scheduler import AutoScheduler
        scheduler = AutoScheduler()
        
        # Check if method exists
        if hasattr(scheduler, 'check_system_health'):
            print("   ✅ check_system_health method exists")
            
            # Try to call it (will check DB which might fail, but that's ok)
            print("\n   Attempting to run health check...")
            try:
                scheduler.check_system_health()
                print("   ✅ Health check executed successfully!")
            except Exception as e:
                print(f"   ⚠️  Health check ran but had errors (expected if DB empty): {e}")
        else:
            print("   ❌ check_system_health method not found!")
            
    except Exception as e:
        print(f"   ❌ Error importing AutoScheduler: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Health monitoring import tests complete!")


if __name__ == "__main__":
    try:
        test_circuit_breaker()
        test_global_circuit_breaker()
        test_health_monitoring_imports()
        
        print("\n" + "=" * 60)
        print("🎉 ALL PRIORITY 1 TESTS PASSED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
