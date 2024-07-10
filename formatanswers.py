import openpyxl

wb = openpyxl.load_workbook("trivia.xlsx")

for sheet in wb.sheetnames:
  specific_sheet = wb[sheet]
  print(f"Starting {sheet}: ")
  for row in specific_sheet:
    if row[3].value != None:
      if '-' in str(row[3].value):
        print(f"Q: {row[2].value} - A: {row[3].value}")
        print("Modify Options:")
        print("1. remove after -")
        print("2. custom")
        print("3. nothing")
        print("4. delete question")
        option_choice = input()

        if option_choice == "1":
          modified_answer = row[3].value.strip().split('-')[0]
          if " " == modified_answer[-1]:
            modified_answer = modified_answer[:-1]
          row[3].value = modified_answer
          print(f"Modified answer: {row[3].value}")
          wb.save("trivia.xlsx")
        elif option_choice == "2":
          row[3].value = input("Custom Input: ")
          wb.save("trivia.xlsx")
        elif option_choice == "3":
          print("Answer not modified.")
        elif option_choice == "4":
          # Delete the current row
          specific_sheet.delete_rows(row.row)  # Delete row at current row index
          print(f"Question deleted.")
          # Important: Decrement the row index to avoid skipping rows after deletion
          row = row.offset(row= -1)  # Move back one row to avoid skipping after deletion
          wb.save("trivia.xlsx")



wb.save("trivia.xlsx")


