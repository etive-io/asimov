"""
Test suites for the prior specification and interface system.
"""

import unittest
from asimov.priors import (
    PriorSpecification,
    PriorDict,
    PriorInterface,
    Reparameterization,
)
# Import BilbyPriorInterface from its new location
try:
    from asimov.pipelines.bilby import BilbyPriorInterface
except ImportError:
    # For testing without full asimov environment
    BilbyPriorInterface = None


class TestPriorSpecification(unittest.TestCase):
    """Test the PriorSpecification model."""
    
    def test_basic_prior(self):
        """Test creating a basic prior specification."""
        prior = PriorSpecification(minimum=10, maximum=1000)
        self.assertEqual(prior.minimum, 10)
        self.assertEqual(prior.maximum, 1000)
        self.assertIsNone(prior.type)
    
    def test_prior_with_type(self):
        """Test creating a prior with a type."""
        prior = PriorSpecification(
            minimum=0,
            maximum=1,
            type="Uniform",
            boundary="periodic"
        )
        self.assertEqual(prior.type, "Uniform")
        self.assertEqual(prior.boundary, "periodic")
    
    def test_powerlaw_prior(self):
        """Test creating a PowerLaw prior."""
        prior = PriorSpecification(
            minimum=10,
            maximum=1000,
            type="PowerLaw",
            alpha=2
        )
        self.assertEqual(prior.alpha, 2)
    
    def test_extra_fields_allowed(self):
        """Test that extra fields are allowed."""
        prior = PriorSpecification(
            minimum=10,
            maximum=1000,
            custom_field="custom_value"
        )
        # Extra fields should be stored
        self.assertTrue(hasattr(prior, '__pydantic_extra__'))


class TestPriorDict(unittest.TestCase):
    """Test the PriorDict model."""
    
    def test_empty_prior_dict(self):
        """Test creating an empty prior dictionary."""
        priors = PriorDict()
        self.assertIsNone(priors.default)
    
    def test_prior_dict_with_default(self):
        """Test creating a prior dictionary with a default."""
        priors = PriorDict(default="BBHPriorDict")
        self.assertEqual(priors.default, "BBHPriorDict")
    
    def test_prior_dict_from_dict(self):
        """Test creating a PriorDict from a plain dictionary."""
        data = {
            "default": "BBHPriorDict",
            "luminosity distance": {
                "minimum": 10,
                "maximum": 1000,
                "type": "PowerLaw",
                "alpha": 2
            },
            "mass ratio": {
                "minimum": 0.1,
                "maximum": 1.0
            }
        }
        priors = PriorDict.from_dict(data)
        self.assertEqual(priors.default, "BBHPriorDict")
        
        # Get a prior
        lum_dist = priors.get_prior("luminosity distance")
        self.assertIsNotNone(lum_dist)
        self.assertEqual(lum_dist.minimum, 10)
        self.assertEqual(lum_dist.maximum, 1000)
    
    def test_prior_dict_to_dict(self):
        """Test converting a PriorDict back to a plain dictionary."""
        data = {
            "default": "BBHPriorDict",
            "mass ratio": {
                "minimum": 0.1,
                "maximum": 1.0
            }
        }
        priors = PriorDict.from_dict(data)
        result = priors.to_dict()
        
        self.assertEqual(result["default"], "BBHPriorDict")
        self.assertIn("mass ratio", result)
        self.assertEqual(result["mass ratio"]["minimum"], 0.1)
    
    def test_get_nonexistent_prior(self):
        """Test getting a prior that doesn't exist."""
        priors = PriorDict(default="BBHPriorDict")
        result = priors.get_prior("nonexistent")
        self.assertIsNone(result)


class TestReparameterization(unittest.TestCase):
    """Test the Reparameterization model."""
    
    def test_basic_reparameterization(self):
        """Test creating a basic reparameterization."""
        reparam = Reparameterization(
            from_parameters=["mass_1", "mass_2"],
            to_parameters=["chirp_mass", "mass_ratio"]
        )
        self.assertEqual(reparam.from_parameters, ["mass_1", "mass_2"])
        self.assertEqual(reparam.to_parameters, ["chirp_mass", "mass_ratio"])
    
    def test_reparameterization_with_transform(self):
        """Test creating a reparameterization with a transform."""
        reparam = Reparameterization(
            from_parameters=["mass_1", "mass_2"],
            to_parameters=["chirp_mass", "mass_ratio"],
            transform="mass_to_chirp_mass_ratio"
        )
        self.assertEqual(reparam.transform, "mass_to_chirp_mass_ratio")


class TestPriorInterface(unittest.TestCase):
    """Test the PriorInterface base class."""
    
    def test_interface_with_none(self):
        """Test creating an interface with no priors."""
        interface = PriorInterface(None)
        self.assertIsNone(interface.prior_dict)
    
    def test_interface_with_dict(self):
        """Test creating an interface with a dictionary."""
        data = {
            "default": "BBHPriorDict",
            "mass ratio": {
                "minimum": 0.1,
                "maximum": 1.0
            }
        }
        interface = PriorInterface(data)
        self.assertIsInstance(interface.prior_dict, PriorDict)
        self.assertEqual(interface.prior_dict.default, "BBHPriorDict")
    
    def test_interface_with_prior_dict(self):
        """Test creating an interface with a PriorDict."""
        priors = PriorDict(default="BBHPriorDict")
        interface = PriorInterface(priors)
        self.assertIs(interface.prior_dict, priors)
    
    def test_interface_validate(self):
        """Test the validate method."""
        interface = PriorInterface(None)
        self.assertTrue(interface.validate())
    
    def test_interface_convert_not_implemented(self):
        """Test that convert raises NotImplementedError."""
        interface = PriorInterface(None)
        with self.assertRaises(NotImplementedError):
            interface.convert()


class TestBilbyPriorInterface(unittest.TestCase):
    """Test the BilbyPriorInterface."""
    
    def setUp(self):
        """Skip tests if BilbyPriorInterface is not available."""
        if BilbyPriorInterface is None:
            self.skipTest("BilbyPriorInterface not available")
    
    def test_bilby_interface_with_none(self):
        """Test bilby interface with no priors."""
        interface = BilbyPriorInterface(None)
        result = interface.convert()
        self.assertEqual(result, {})
    
    def test_bilby_interface_convert(self):
        """Test bilby interface conversion."""
        data = {
            "default": "BBHPriorDict",
            "luminosity distance": {
                "minimum": 10,
                "maximum": 1000,
                "type": "PowerLaw",
                "alpha": 2
            }
        }
        interface = BilbyPriorInterface(data)
        result = interface.convert()
        
        self.assertEqual(result["default"], "BBHPriorDict")
        self.assertIn("luminosity distance", result)
    
    def test_bilby_default_prior(self):
        """Test getting the default prior."""
        interface = BilbyPriorInterface(None)
        default = interface.get_default_prior()
        self.assertEqual(default, "BBHPriorDict")
        
        interface = BilbyPriorInterface({"default": "BNSPriorDict"})
        default = interface.get_default_prior()
        self.assertEqual(default, "BNSPriorDict")


class TestBackwardCompatibility(unittest.TestCase):
    """Test that the new system is backward compatible with existing blueprints."""
    
    def test_simple_prior_dict(self):
        """Test a simple prior dictionary like in existing blueprints."""
        data = {
            "luminosity distance": {
                "minimum": 10,
                "maximum": 10000
            },
            "mass ratio": {
                "minimum": 0.05,
                "maximum": 1.0
            }
        }
        priors = PriorDict.from_dict(data)
        result = priors.to_dict()
        
        # Should preserve the structure
        self.assertIn("luminosity distance", result)
        self.assertEqual(result["luminosity distance"]["minimum"], 10)
    
    def test_complex_prior_dict(self):
        """Test a complex prior dictionary from actual blueprints."""
        data = {
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
        # Should not raise an exception
        priors = PriorDict.from_dict(data)
        result = priors.to_dict()
        
        # Verify structure is preserved
        self.assertIn("chirp mass", result)
        self.assertEqual(result["chirp mass"]["minimum"], 21.418182160215295)


if __name__ == "__main__":
    unittest.main()
