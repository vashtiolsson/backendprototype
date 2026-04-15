CSN_MAPPING = {
    "support_type": [
        {
            "table": "studiestodsarende",
            "field": "stodform_klartext",
            "priority": 1,
            "transform": "identity1",
        },
        {
            "table": "studiestodsarende",
            "field": "studiestodstyp",
            "priority": 2,
            "transform": "identity1",
        },
        {"table": "studieform_kod", 
         "field": "studieform_kod", 
         "priority": 3, 
         "transform": "identity1"
         },

         {"table": "beviljat_belopp", 
         "field": "beloppstyp_klartext", 
         "priority": 1, 
         "transform": "identity2"
         },

         {"table": "beviljat_belopp", 
          "field": "studieform_kod", 
          "priority": 2, 
          "transform": "identity2"
          }
         
    ],

    "time_period": [
        {
            "table": "beviljad_period",
            "field": ["starttid", "sluttid"],
            "priority": 1,
            "transform": "combine_period",
        },
    ],
    "amount": [
        {
            "table": "beviljat_belopp",
            "where": {"beloppstyp": "GRUNDB"},
            "field": "belopp_per_vecka",
            "priority": 1,
            "transform": "sek_per_week_label",
        },
        {
            "table": "beviljat_belopp",
            "where": {"beloppstyp": "GRUNDL"},
            "field": "belopp_per_vecka",
            "priority": 2,
            "transform": "sek_per_week_label",
        },
        {
            "table": "beviljad_period",
            "field": "totalt_belopp",
            "priority": 3,
            "transform": "sek_total_label",
        },
    ],
}