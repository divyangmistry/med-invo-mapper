import sys
from unittest.mock import MagicMock

# Mock dependencies that might be missing on host
sys.modules['pytesseract'] = MagicMock()
sys.modules['PIL'] = MagicMock()
sys.modules['PIL.Image'] = MagicMock()
sys.modules['PIL.ImageEnhance'] = MagicMock()
sys.modules['PIL.ImageFilter'] = MagicMock()

from pathlib import Path
import unittest
from unittest.mock import patch

# Add agent dir to path
sys.path.append(str(Path(__file__).parent.parent / "agent"))

from extractor import ExtractionResult, MedicineItem, _parse_json_from_text
from database import log_transaction
from excel_writer import append_to_excel

class TestMultiEntryOCR(unittest.TestCase):
    def test_extraction_result_model(self):
        data = {
            "vendor_name": "Test Vendor",
            "invoice_number": "INV-001",
            "items": [
                {
                    "medicine_name": "Paracetamol",
                    "medicine_code": "P123",
                    "batch_number": "B001",
                    "manufacturing_date": "01/2023",
                    "expiry_date": "01/2025",
                    "quantity": 10
                },
                {
                    "medicine_name": "Amoxicillin",
                    "medicine_code": "A456",
                    "batch_number": "B002",
                    "manufacturing_date": "02/2023",
                    "expiry_date": "02/2025",
                    "quantity": 5
                }
            ]
        }
        result = ExtractionResult(**data)
        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.vendor_name, "Test Vendor")
        self.assertTrue(result.critical_fields_present)

    def test_json_parsing_multi_item(self):
        raw_response = """
        Some thinking...
        ```json
        {
          "vendor_name": "Pharma Corp",
          "invoice_number": "2024-99",
          "items": [
            {"medicine_name": "Med A", "medicine_code": "MA", "batch_number": "BN1", "expiry_date": "10/2025", "quantity": 1},
            {"medicine_name": "Med B", "medicine_code": "MB", "batch_number": "BN2", "expiry_date": "11/2025", "quantity": 2}
          ]
        }
        ```
        """
        parsed = _parse_json_from_text(raw_response)
        self.assertEqual(len(parsed["items"]), 2)
        self.assertEqual(parsed["vendor_name"], "Pharma Corp")

    def test_json_parsing_repairs_missing_value(self):
        raw_response = """
        ```json
        {
          "vendor_name": "X",
          "invoice_number": "Y",
          "items": [
            {
              "medicine_name": "A",
              "medicine_code": "C1",
              "batch_number": "B1",
              "expiry_date": "10/2025",
              "ptr":
            }
          ]
        }
        ```
        """
        parsed = _parse_json_from_text(raw_response)
        self.assertEqual(parsed["vendor_name"], "X")
        self.assertEqual(parsed["items"][0]["ptr"], None)

    @patch("database.get_session")
    @patch("database.get_or_create_vendor")
    @patch("database.get_or_create_medicine")
    @patch("database.upsert_mapping")
    def test_database_logging_multi_item(self, mock_upsert, mock_get_med, mock_get_vendor, mock_get_session):
        mock_vendor = MagicMock()
        mock_vendor.id = 1
        mock_get_vendor.return_value = mock_vendor
        
        mock_med = MagicMock()
        mock_med.id = 10
        mock_get_med.return_value = mock_med
        
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        extraction_dict = {
            "vendor_name": "V",
            "invoice_number": "I",
            "items": [
                {"medicine_name": "M1", "medicine_code": "C1", "batch_number": "B1", "expiry_date": "E1", "quantity": 1},
                {"medicine_name": "M2", "medicine_code": "C2", "batch_number": "B2", "expiry_date": "E2", "quantity": 2}
            ]
        }
        
        txns = log_transaction(extraction_dict, source_image="test.jpg")
        
        self.assertEqual(len(txns), 2)
        self.assertEqual(mock_get_med.call_count, 2)
        self.assertEqual(mock_session.add.call_count, 2)
        mock_session.commit.assert_called_once()

if __name__ == "__main__":
    unittest.main()
