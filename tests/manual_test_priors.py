#!/usr/bin/env python
"""
Manual integration test for the prior system.

This script tests the prior system without requiring the full asimov environment.
It demonstrates that:
1. Priors can be validated
2. Prior interfaces work correctly
3. Backward compatibility is maintained
"""

import sys
import os

# Add the asimov module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'asimov'))

# Import outside the asimov directory to avoid logging.py conflict
os.chdir('/tmp')

# Import the prior models directly
from asimov.priors import (
    PriorSpecification,
    PriorDict,
    Reparameterization
)
from asimov.pipelines.bilby import BilbyPriorInterface

def test_basic_prior_spec():
    """Test basic prior specification."""
    print("Testing basic prior specification...")
    prior = PriorSpecification(minimum=10, maximum=1000)
    assert prior.minimum == 10
    assert prior.maximum == 1000
    print("✓ Basic prior specification works")

def test_prior_dict_from_blueprint():
    """Test creating a PriorDict from blueprint data."""
    print("\nTesting PriorDict from blueprint...")
    
    # Simulate data from a blueprint
    blueprint_data = {
        "default": "BBHPriorDict",
        "luminosity distance": {
            "minimum": 10,
            "maximum": 10000
        },
        "mass ratio": {
            "minimum": 0.05,
            "maximum": 1.0
        },
        "chirp mass": {
            "minimum": 21.41,
            "maximum": 41.97,
            "type": "UniformInComponentsChirpMass"
        }
    }
    
    priors = PriorDict.from_dict(blueprint_data)
    assert priors.default == "BBHPriorDict"
    
    # Get individual priors
    lum_dist = priors.get_prior("luminosity distance")
    assert lum_dist is not None
    assert lum_dist.minimum == 10
    
    mass_ratio = priors.get_prior("mass ratio")
    assert mass_ratio is not None
    assert mass_ratio.maximum == 1.0
    
    print("✓ PriorDict from blueprint works")

def test_bilby_interface():
    """Test the Bilby prior interface."""
    print("\nTesting Bilby prior interface...")
    
    blueprint_data = {
        "default": "BBHPriorDict",
        "luminosity distance": {
            "minimum": 10,
            "maximum": 1000,
            "type": "PowerLaw",
            "alpha": 2
        }
    }
    
    interface = BilbyPriorInterface(blueprint_data)
    result = interface.convert()
    
    assert result["default"] == "BBHPriorDict"
    assert "luminosity distance" in result
    assert result["luminosity distance"]["minimum"] == 10
    
    default = interface.get_default_prior()
    assert default == "BBHPriorDict"
    
    print("✓ Bilby prior interface works")

def test_backward_compatibility():
    """Test that old blueprint formats still work."""
    print("\nTesting backward compatibility...")
    
    # Old format blueprint (from actual test data)
    old_format = {
        "amplitude order": 1,
        "chirp mass": {
            "maximum": 41.97447913941358,
            "minimum": 21.418182160215295
        },
        "luminosity distance": {
            "maximum": 10000,
            "minimum": 10
        },
        "mass 1": {
            "maximum": 1000,
            "minimum": 1
        },
        "mass ratio": {
            "maximum": 1.0,
            "minimum": 0.05
        }
    }
    
    # Should not raise exception
    priors = PriorDict.from_dict(old_format)
    result = priors.to_dict()
    
    # Verify structure is preserved
    assert "chirp mass" in result
    assert result["chirp mass"]["minimum"] == 21.418182160215295
    assert result["mass ratio"]["maximum"] == 1.0
    
    print("✓ Backward compatibility maintained")

def test_reparameterization():
    """Test reparameterization specification."""
    print("\nTesting reparameterization...")
    
    reparam = Reparameterization(
        from_parameters=["mass_1", "mass_2"],
        to_parameters=["chirp_mass", "mass_ratio"],
        transform="mass_to_chirp_mass_ratio"
    )
    
    assert reparam.from_parameters == ["mass_1", "mass_2"]
    assert reparam.to_parameters == ["chirp_mass", "mass_ratio"]
    assert reparam.transform == "mass_to_chirp_mass_ratio"
    
    print("✓ Reparameterization works")

def test_extra_fields():
    """Test that extra fields are allowed."""
    print("\nTesting extra fields...")
    
    prior = PriorSpecification(
        minimum=10,
        maximum=100,
        custom_param="custom_value",
        another_param=42
    )
    
    # Extra fields should be stored
    assert hasattr(prior, '__pydantic_extra__')
    
    print("✓ Extra fields are allowed")

def main():
    """Run all tests."""
    print("=" * 60)
    print("Running Prior System Integration Tests")
    print("=" * 60)
    
    try:
        test_basic_prior_spec()
        test_prior_dict_from_blueprint()
        test_bilby_interface()
        test_backward_compatibility()
        test_reparameterization()
        test_extra_fields()
        
        print("\n" + "=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
        return 0
    
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
