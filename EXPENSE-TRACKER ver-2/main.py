import json

def load_expenses():
    try:
        with open("expenses.json","r")as file:
             return json.load(file)
    except FileNotFoundError:
         return[]

def save_expences(expenses):
    with open("expenses.json","w")as file:
          json.dump(expenses,file,indent=4)

def add_expenses(expenses):
    while True:
        try:
            amount = float(input("Enter the amount: "))

            if amount <= 0:
                print("Amount must be greater than 0.")
                continue

            break

        except ValueError:
            print("Please enter a valid number.")
    while True:
        category = input("Enter the category: ")
        if category.strip()=="":
             print("the category cannot be empty")
        else:
             break
    while True:
        description=input("enter the description:")
        if description.strip()=="":
                print("the description cannot be empty")
        else:
             break
    while True:
       date=input("enter the date dd-mm-yyyy:")
       try:
          day,month,year=date.split("-")
          if len(day)==2 and len(month)==2 and len(year)==4:
               break
          else:
               print("please enter the valid date")
       except ValueError:
            print("please use dd-mm-yyyy format")
    expense = {
          "amount":amount,
          "category":category,
          "description":description,
          "date":date
     }
    expenses.append(expense)
    save_expences(expenses)

def view_expences(expenses):
     if not expenses:
          print("no expences found")
          return
     print("\nall expences:")
     for i,expense in enumerate(expenses,start=1):
          print(
               f"{i}.${expense['amount']}|"
               f"{expense['category']}|"
               f"{expense['description']}|"
               f"{expense['date']}"
          )


def total_expenses(expenses):
     total=0
     for expense in expenses:
          total+=expense["amount"]
     print(f"total spending:${total:.2f}")


def higest_expense(expenses):
     if not expenses:
          print("no expense found")
          return
     higest=expenses[0]
     for expense in expenses:
          if expense["amount"]>higest["amount"]:
               higest=expense
     print(f"higest amount:${higest['amount']}")


def filter_by_category(expenses):
     category=input("enter the category:")
     found=False
     for expense in expenses:
          if expense["category"].lower()==category.lower():
               print(
                    f"${expense['amount']}|"
                    f"{expense['category']}|"
                    f"{expense['description']}|"
                    f"{expense['date']}"
               )
               found=True
          if not found:
               print("the category of expense cannot be found")


def add_mainmenu():
     expenses=load_expenses()
     while True:
          print("=======expense tracker=========")
          print("1. add an expense")
          print("2. view expenses")
          print("3. total expenses")
          print("4. higest expenses")
          print("5. filter by category")
          print("6. exit")
          choice=input("enter your choice:")
          if choice=="1":add_expenses(expenses)
          elif choice=="2":view_expences(expenses)
          elif choice=="3":total_expenses(expenses)
          elif choice=="4":higest_expense(expenses)
          elif choice=="5":filter_by_category(expenses)
          elif choice=="6":
               print("thankyou for using expense tracker")
               break
          else:
               print("invalid choice enter the choice between 1-6")
add_mainmenu()


