import unittest

from app.logic import clear_results_missing_fields, extract_results_reference


class ResultsProgressionLogicTests(unittest.TestCase):
    def test_extracts_sample_reference_when_message_has_digits(self) -> None:
        result = extract_results_reference("Mi muestra es 12345")
        self.assertEqual(result.get("sample_reference"), "12345")

    def test_extracts_pet_name_when_message_has_name(self) -> None:
        result = extract_results_reference("Jorgito")
        self.assertEqual(result.get("pet_name"), "Jorgito")

    def test_ignores_greeting_as_reference(self) -> None:
        result = extract_results_reference("Hola")
        self.assertEqual(result, {})

    def test_ignores_sample_submission_phrase_as_results_reference(self) -> None:
        result = extract_results_reference("Hola, quiero analizar una muestra")
        self.assertEqual(result, {})

    def test_clears_results_related_missing_fields(self) -> None:
        missing_fields = [
            "numero de muestra o nombre mascota",
            "direccion",
            "numero de orden",
        ]
        cleaned = clear_results_missing_fields(missing_fields)
        self.assertEqual(cleaned, ["direccion"])


if __name__ == "__main__":
    unittest.main()
