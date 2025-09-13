# app/services/facebook_category_mapper.py
# Smart mapping of Facebook forms to LeadG CRM categories

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class FacebookCategoryMapper:
    """Maps Facebook lead form names to CRM categories"""
    
    def __init__(self):
        # Mapping rules based on your actual forms
        self.form_mappings = {
            # Nursing forms → "Nursing" category
            "nursing_keywords": ["nurse", "nursing", "rn", "lpn", "healthcare"],
            "nursing_category": "Nursing",
            
            # Work abroad forms → "Work Abroad" category  
            "work_keywords": ["worker", "work", "job", "employment"],
            "work_category": "Work Abroad",
            
            # Study abroad forms → "Study Abroad" category
            "study_keywords": ["europe", "uk", "study", "abroad", "german", "germen", "language", "deutsch"],
            "study_category": "Study Abroad",
            
            # Fallback category
            "fallback_category": "Facebook_General"
        }
    
    def map_form_to_category(self, form_name: str) -> Dict[str, Any]:
        """
        Map Facebook form name to CRM category
        Priority: Nursing > Work Abroad > Study Abroad > General
        
        Args:
            form_name: Name of the Facebook lead form
            
        Returns:
            Dict with category, confidence, and reasoning
        """
        try:
            form_lower = form_name.lower()
            
            # PRIORITY 1: Check for nursing keywords (highest priority)
            nursing_matches = [kw for kw in self.form_mappings["nursing_keywords"] if kw in form_lower]
            if nursing_matches:
                return {
                    "category": self.form_mappings["nursing_category"],
                    "confidence": "high",
                    "reasoning": f"Form contains nursing-related keywords (priority rule)",
                    "matched_keywords": nursing_matches,
                    "priority_level": 1
                }
            
            # PRIORITY 2: Check for work abroad keywords  
            work_matches = [kw for kw in self.form_mappings["work_keywords"] if kw in form_lower]
            if work_matches:
                return {
                    "category": self.form_mappings["work_category"],
                    "confidence": "high", 
                    "reasoning": f"Form contains work-related keywords",
                    "matched_keywords": work_matches,
                    "priority_level": 2
                }
            
            # PRIORITY 3: Check for study abroad keywords
            study_matches = [kw for kw in self.form_mappings["study_keywords"] if kw in form_lower]
            if study_matches:
                return {
                    "category": self.form_mappings["study_category"],
                    "confidence": "high",
                    "reasoning": f"Form contains study/language-related keywords", 
                    "matched_keywords": study_matches,
                    "priority_level": 3
                }
            
            # PRIORITY 4: Fallback to general category
            else:
                return {
                    "category": self.form_mappings["fallback_category"],
                    "confidence": "low",
                    "reasoning": "No matching keywords found, using fallback category",
                    "matched_keywords": [],
                    "priority_level": 4
                }
                
        except Exception as e:
            logger.error(f"Error mapping form '{form_name}' to category: {str(e)}")
            return {
                "category": self.form_mappings["fallback_category"],
                "confidence": "error",
                "reasoning": f"Error during mapping: {str(e)}",
                "matched_keywords": []
            }
    
    def preview_mappings(self, form_names: list) -> Dict[str, Dict[str, Any]]:
        """Preview how forms would be mapped to categories"""
        return {
            form_name: self.map_form_to_category(form_name) 
            for form_name in form_names
        }
    
    def get_mapping_statistics(self, form_names: list) -> Dict[str, Any]:
        """Get statistics about form mappings"""
        mappings = self.preview_mappings(form_names)
        
        category_counts = {}
        confidence_counts = {"high": 0, "low": 0, "error": 0}
        
        for form_name, mapping in mappings.items():
            category = mapping["category"]
            confidence = mapping["confidence"]
            
            category_counts[category] = category_counts.get(category, 0) + 1
            confidence_counts[confidence] += 1
        
        return {
            "total_forms": len(form_names),
            "category_distribution": category_counts,
            "confidence_distribution": confidence_counts,
            "high_confidence_percentage": (confidence_counts["high"] / len(form_names)) * 100
        }

# Create service instance
facebook_category_mapper = FacebookCategoryMapper()

# Test with your actual forms
if __name__ == "__main__":
    test_forms = [
        "Skillang -Nurse -Kerala belt",
        "3 questio Skillang Nursing - Nagercoil", 
        "2 Question Skillang German Nurses forum-copy",
        "Skillang -Germen Lan - Nagarcoil",
        "Skillang -Germen A1 Offline - Leads",
        "Skillang - Europe Leads",
        "Skillang - Study aboard UK -Leads"
    ]
    
    mapper = FacebookCategoryMapper()
    preview = mapper.preview_mappings(test_forms)
    stats = mapper.get_mapping_statistics(test_forms)
    
    print("Form Mapping Preview:")
    for form, mapping in preview.items():
        print(f"'{form}' → {mapping['category']} ({mapping['confidence']} confidence)")
    
    print(f"\nMapping Statistics:")
    print(f"High confidence mappings: {stats['high_confidence_percentage']:.1f}%")
    print(f"Category distribution: {stats['category_distribution']}")