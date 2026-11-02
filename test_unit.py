"""
test_unit.py - Модульные тесты для логики классификации, фильтрации, соцсетей и генерации запросов.
"""

import unittest
from gender_classifier import classify_host
from filter_hosts import (
    HostFilter,
    detect_secret_code,
    extract_sleeping_arrangement,
    extract_house_rules,
    clean_text,
)
from social_extractor import extract_instagram
from message_generator import generate_stay_request, format_date_range


class TestGenderClassifier(unittest.TestCase):
    def test_male_classification(self):
        gender, h_type = classify_host("Ryu I.", "Fit Japanese from Tokyo", "ryu-tokyo")
        self.assertEqual(gender, "Male")
        self.assertEqual(h_type, "solo")

        gender, h_type = classify_host("Takumi T.", "Solo adventure boy", "takumitezuka")
        self.assertEqual(gender, "Male")
        self.assertEqual(h_type, "solo")

        gender, h_type = classify_host("Koji A.", "Working in tech", "kojiarie")
        self.assertEqual(gender, "Male")

        gender, h_type = classify_host("Kentaro S.", "I don't host single female traveler", "kentaro-shibamoto")
        self.assertEqual(gender, "Male")

    def test_female_classification(self):
        gender, h_type = classify_host("Sakura M.", "Welcome to Tokyo", "sakura-tokyo")
        self.assertEqual(gender, "Female")
        self.assertEqual(h_type, "solo")

        gender, h_type = classify_host("Nozomi T.", "Solo traveler", "nozomi-nozomi-1")
        self.assertEqual(gender, "Female")

        gender, h_type = classify_host("Ai T.", "The girl who walks", "thegirlwhowalks")
        self.assertEqual(gender, "Female")

    def test_couple_classification(self):
        gender, h_type = classify_host("Ken & Yoko", "We live in Shibuya", "ken_yoko")
        self.assertEqual(gender, "Couple")
        self.assertEqual(h_type, "couple")

        gender, h_type = classify_host("Alex", "I live with my boyfriend in Tokyo", "alex_tokyo")
        self.assertEqual(gender, "Couple")
        self.assertEqual(h_type, "couple")


class TestSocialExtractor(unittest.TestCase):
    def test_instagram_extraction(self):
        url, handle = extract_instagram("Hi!! I’m Yuki from Japan. instagram.com/iamyukiyamada/ I love traveling")
        self.assertEqual(handle, "iamyukiyamada")
        self.assertEqual(url, "https://www.instagram.com/iamyukiyamada/")

        url, handle = extract_instagram("My Instagram: @boku___20___ — 36K followers")
        self.assertEqual(handle, "boku___20___")
        self.assertEqual(url, "https://www.instagram.com/boku___20___/")

        url, handle = extract_instagram("■Instagram @dan_ryo_yoshi")
        self.assertEqual(handle, "dan_ryo_yoshi")
        self.assertEqual(url, "https://www.instagram.com/dan_ryo_yoshi/")

        url, handle = extract_instagram("I have no social media.")
        self.assertEqual(handle, "")
        self.assertEqual(url, "")


class TestMessageGenerator(unittest.TestCase):
    def test_date_range_formatting(self):
        formatted = format_date_range("2026-11-11", "2026-11-14")
        self.assertIn("Nov 11th – 14th, 2026", formatted)

    def test_stay_request_structure(self):
        host = {
            "name": "Koji A.",
            "clean_name": "Koji",
            "about_me_clean": "I love good food, ramen and creative design.",
            "sleeping_arrangement": "Private Room",
            "secret_code_hint": "tokyo_ramen",
            "secret_code_detected": True,
        }
        msg = generate_stay_request(host, "2026-11-11", "2026-11-14")
        self.assertIn("Hi Koji!", msg)
        self.assertIn("Nov 11th – 14th, 2026", msg)
        self.assertIn("Club Med Tomamu", msg)
        self.assertIn("ski instructor", msg)
        self.assertIn("10 years", msg)
        self.assertIn("private room", msg.lower())
        self.assertIn("tokyo_ramen", msg)


class TestFilterAndExtraction(unittest.TestCase):
    def setUp(self):
        self.filter = HostFilter()

    def test_stop_triggers_exclusion(self):
        t1 = self.filter.check_stop_triggers("*NOT ACCEPTING GUESTS NOW Into cross-cultural communication")
        self.assertTrue(len(t1) > 0)
        self.assertIn("not accepting guests", t1)

        t2 = self.filter.check_stop_triggers("I'm back in Japan, but I'm far away from Tokyo for a while and cannot host anyone right now. Please refrain from sending stay requests")
        self.assertTrue(len(t2) > 0)
        self.assertIn("cannot host", t2)

        t3 = self.filter.check_stop_triggers("*Currently not in Japan* I'm just a modest boy who is full of curiosity")
        self.assertTrue(len(t3) > 0)
        self.assertIn("currently not in japan", t3)

        t4 = self.filter.check_stop_triggers("Currently on a working holiday in Perth, WA, Australia! People with crooked glasses...")
        self.assertTrue(len(t4) > 0)
        self.assertIn("working holiday", t4)

        t5 = self.filter.check_stop_triggers("We can host only for one night. If you need more than one night, please check our listing on Airbnb.")
        self.assertTrue(len(t5) > 0)
        self.assertIn("airbnb", t5)
        self.assertIn("only for one night", t5)

    def test_secret_code_detection(self):
        has_code, code = detect_secret_code("If you've read my description, please write 'holyfalcon' in your request")
        self.assertTrue(has_code)
        self.assertEqual(code, "holyfalcon")

        has_code, code = detect_secret_code("The secret word is sakura2026")
        self.assertTrue(has_code)
        self.assertEqual(code, "sakura2026")

        has_code, code = detect_secret_code("I ONLY HOST PEOPLE WHO READ MY ENTIRE PROFILE BEFORE SENDING A REQUEST")
        self.assertTrue(has_code)
        self.assertIn("Profile reading required", code)

    def test_sleeping_arrangement_extraction(self):
        self.assertEqual(extract_sleeping_arrangement("You will sleep in a Private Room with a lock"), "Private Room")
        self.assertEqual(extract_sleeping_arrangement("We offer a shared room with bunk beds"), "Shared Room")
        self.assertEqual(extract_sleeping_arrangement("Couch in the living room / common area"), "Common Area / Couch")

    def test_house_rules_extraction(self):
        rules = extract_house_rules("No smoking inside. Late nights okay. Please respect quiet hours.")
        self.assertIn("No smoking", rules)
        self.assertIn("Late nights okay", rules)


if __name__ == "__main__":
    unittest.main()
