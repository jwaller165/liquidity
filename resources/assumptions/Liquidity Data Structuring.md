%md


#What happens next? 

--> Table Mapping Guide 
    --> Staging tables 
    --> Add how the source tables create the staging tables (have sections for mapping queries ... (i.e. what is brokered, counterparty types, commerical v ind. ... etc))
    --> Have the rules for odm to show the transformation.
    --> Add timestamp and updates to add assumptions updates 
    



1. Source table
2. Rules for transformation
3. Staging tables (ready for model)
4. Run ODM  .... 

5. Be sure to tighten up how the versions are configured 
 -- Develop process to create run types (Y/N)
  -- 1) Offical Run (only those that say offical can be pulled dowstream)
  -- 2) Test Run (new ideas, test)
  -- 3) Pending Status
  -- IDEA) When run type is pending then email (Vlad, Matthew, Eddie, JM) with the agg run results 


  (POST RUN STATUS ... edit)
    -- Do not batch runs for old runs (Only 1 month at a time to reduce the potential of old data causing a new results)

    
Add columns to show driver of ops... 

-- Show Spot, 75th txn bal, 75th avg balance -- and winner (min) ... why are they operational?






