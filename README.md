## Authentication system
A verification dependency decompile the JWT that came on the auth headers to extract the `sub` field. 
This `sub` field is used to related a specific generation to the users which started it. 

**From where is this token came from?**
The received token cames from a third party auth provider. For example, by using the "login with Google" button on the frontend, the frontend will get an `idToken` that will be sended on the auth headers. 

**For what is this authentication used for**
- On the generation endpoint: Stores this id on the `user_id` column of the `VideoRecord` table. 
- On getters: asserts that the requested generations corresponds to the user who's calling. 
- Helps to find all user's related generations to return a list of them. 
- Used to know the usage of each specific user, so them can be billed accordlingly. 