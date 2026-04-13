import os
import re
from collections import defaultdict

def analyze_report(filepath="../../data/evaluation_report.md"):
    # Dynamically locate the report based on the script's location
    actual_path = os.path.join(os.path.dirname(__file__), filepath)
    
    if not os.path.exists(actual_path):
        print("🚨 Error: No evaluation report found. The Council has not convened yet.")
        return

    # Dictionaries and lists to hold scores
    judge_scores = defaultdict(list)
    chief_judge_scores = []

    # Regex patterns specifically tuned to the Markdown formatting
    junior_pattern = re.compile(r"\|\s*\*\*(Judge.*?)\*\*\s*\|\s*(\d)/5\s*\|")
    chief_pattern = re.compile(r"\*\*Chief Judge Score:\*\*\s*(\d)/5")

    # Parse the Markdown file line by line
    with open(actual_path, "r", encoding="utf-8") as f:
        for line in f:
            # Look for Junior Council scores
            junior_match = junior_pattern.search(line)
            if junior_match:
                judge_name = junior_match.group(1)
                score = int(junior_match.group(2))
                judge_scores[judge_name].append(score)
            
            # Look for Chief Judge scores
            chief_match = chief_pattern.search(line)
            if chief_match:
                score = int(chief_match.group(1))
                chief_judge_scores.append(score)

    # Print the final analytics dashboard
    print("\n" + "="*60)
    print("📊 MEGA-CITY ONE: ACADEMY INSTRUCTOR DASHBOARD 📊")
    print("="*60)
    
    print("\n[COUNCIL MEMBER AVERAGES]")
    for judge, scores in judge_scores.items():
        avg = sum(scores) / len(scores) if scores else 0
        print(f" - {judge}: {avg:.2f} / 5.00 (from {len(scores)} rulings)")

    print("\n[⚖️ CHIEF JUDGE FINAL APPROVAL RATING]")
    if chief_judge_scores:
        chief_avg = sum(chief_judge_scores) / len(chief_judge_scores)
        print(f" Overall Supreme Score: {chief_avg:.2f} / 5.00")
        
        if chief_avg >= 4.5:
            print(" Status: OUTSTANDING. The Instructor is serving the city well.")
        elif chief_avg >= 3.0:
            print(" Status: ACCEPTABLE. The Instructor requires minor recalibration.")
        else:
            print(" Status: FAIL. The Instructor is hallucinating. Send to Iso-Cubes.")
    else:
        print(" No Chief Judge decrees found.")
    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    analyze_report()