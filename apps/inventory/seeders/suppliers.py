from apps.core.constants import STATUS_ACTIVE
from apps.inventory.models import Supplier

SUPPLIERS = [
    # code, name, city_name, addr1, tel1, email, ntn, sector
    ("SUP001", "Al-Fatah Traders", "Lahore", "23-B Gulberg III, Lahore", "042-35761234", "info@alfatahtraders.com.pk", "1234567-1"),
    ("SUP002", "Pak Steel Industries", "Karachi", "Plot 45 SITE Industrial Area, Karachi", "021-32561890", "sales@paksteel.com.pk", "2345678-2"),
    ("SUP003", "Hafeez & Sons Enterprises", "Faisalabad", "Chowk Azam Road, Faisalabad", "041-26789012", "hafeezandsons@gmail.com", "3456789-3"),
    ("SUP004", "National Chemicals Pvt Ltd", "Karachi", "I-9 Industrial Zone, Karachi", "021-34512678", "ncp@nationalchem.pk", "4567890-4"),
    ("SUP005", "Crescent Textile Mills", "Faisalabad", "Jaranwala Road, Faisalabad", "041-28901234", "procurement@crescenttex.pk", "5678901-5"),
    ("SUP006", "Arif Brothers Hardware", "Rawalpindi", "Raja Bazar, Rawalpindi", "051-45678901", "arifbrothers@hotmail.com", "6789012-6"),
    ("SUP007", "Punjab Plastic Works", "Lahore", "Kot Lakhpat Industrial Estate, Lahore", "042-35128890", "ppw@punjabplastic.pk", "7890123-7"),
    ("SUP008", "Bilal Electricals", "Karachi", "Bolton Market, Karachi", "021-32145678", "bilalelectricals@yahoo.com", "8901234-8"),
    ("SUP009", "Rehman Pharmaceuticals", "Lahore", "Scheme Mor, Lahore", "042-36512340", "info@rehmanpharma.pk", "9012345-9"),
    ("SUP010", "Sitara Energy Ltd", "Faisalabad", "Khurrianwala, Faisalabad", "041-23456789", "sitara@sitaraenergy.pk", "0123456-0"),
    ("SUP011", "Kohinoor Spinning Mills", "Lahore", "47-D Gulberg II, Lahore", "042-35712340", "procurement@kohinoor.pk", "1122334-4"),
    ("SUP012", "Ahmed Trading Company", "Multan", "Hussain Agahi, Multan", "061-45123890", "ahmed.trading@gmail.com", "2233445-5"),
    ("SUP013", "Karachi Steel Works", "Karachi", "Landhi Industrial Area, Karachi", "021-35814567", "ksw@karachisteel.pk", "3344556-6"),
    ("SUP014", "Islamabad Office Supplies", "Islamabad", "F-10 Markaz, Islamabad", "051-28901235", "ios@officesupplies.pk", "4455667-7"),
    ("SUP015", "Quetta Mineral Resources", "Quetta", "Brewery Road, Quetta", "081-45678902", "qmr@quettaminerals.pk", "5566778-8"),
    ("SUP016", "Gul Ahmed Textile", "Karachi", "West Wharf Road, Karachi", "021-32112345", "b2b@gulahmed.pk", "6677889-9"),
    ("SUP017", "Master Foam Pvt Ltd", "Lahore", "Main Raiwind Road, Lahore", "042-37891234", "masterfoam@masterfoam.pk", "7788990-0"),
    ("SUP018", "Packages Limited", "Lahore", "Shahrah-e-Roomi, Lahore", "042-35761000", "info@packages.com.pk", "8899001-1"),
    ("SUP019", "Attock Cement Company", "Rawalpindi", "ARL Road, Rawalpindi", "051-56789012", "acc@attockcement.pk", "9900112-2"),
    ("SUP020", "Thal Industries", "Karachi", "S.I.T.E., Karachi", "021-32567891", "thal@thalind.pk", "0011223-3"),
    ("SUP021", "Zahid Jee Textile", "Faisalabad", "Sargodha Road, Faisalabad", "041-28765432", "zjt@zahidjee.pk", "1234509-8"),
    ("SUP022", "Maple Leaf Cement", "Lahore", "GT Road, Daud Khel", "042-35234561", "mlc@mapleleaf.pk", "2345610-9"),
    ("SUP023", "Ali Gohar Rice Mills", "Sialkot", "Sambrial Road, Sialkot", "052-34512780", "agr@aligohar.pk", "3456721-0"),
    ("SUP024", "Siddiqsons Steel", "Karachi", "Bin Qasim Industrial Zone", "021-34672891", "siddiqsons@siddiqsons.pk", "4567832-1"),
    ("SUP025", "Interwood Mobel", "Karachi", "Korangi Industrial Area", "021-35112345", "corporate@interwood.com.pk", "5678943-2"),
    ("SUP026", "Noon Sugar Mills", "Sahiwal", "Bhai Pheru Road, Sahiwal", "040-45678901", "noon@noonsugar.pk", "6789054-3"),
    ("SUP027", "Bismillah Enterprises", "Lahore", "Badami Bagh, Lahore", "042-37123456", "bismillah@gmail.com", "7890165-4"),
    ("SUP028", "Cherat Cement Co", "Peshawar", "GT Road, Nowshera", "091-45678901", "cherat@cheratcement.pk", "8901276-5"),
    ("SUP029", "Engro Fertilizers", "Karachi", "Harbour Front, Karachi", "021-35297000", "efert@engro.com", "9012387-6"),
    ("SUP030", "Lucky Cement", "Karachi", "Pezu, D.I. Khan (HO Karachi)", "021-34320301", "lucky@luckycement.com", "0123498-7"),
    ("SUP031", "Naveena Industries", "Karachi", "S.I.T.E. Superhighway", "021-32145679", "naveena@naveena.pk", "1234560-0"),
    ("SUP032", "Ibrahim Fibres", "Faisalabad", "Jaranwala Road, Faisalabad", "041-28901236", "if@ibrahimfibres.pk", "2345671-1"),
    ("SUP033", "Samin Textiles", "Faisalabad", "Sammundri Road, Faisalabad", "041-23456790", "samin@samin.pk", "3456782-2"),
    ("SUP034", "Aisha Steel Mills", "Karachi", "Bin Qasim, Karachi", "021-34761234", "aisha@aishasteel.pk", "4567893-3"),
    ("SUP035", "Amreli Steels", "Karachi", "Superhighway, Karachi", "021-38901234", "amreli@amrelisteels.pk", "5678904-4"),
    ("SUP036", "Mughal Iron & Steel", "Lahore", "Sheikhupura Road, Lahore", "042-37891235", "mughal@mughalsteel.pk", "6789015-5"),
    ("SUP037", "International Industries", "Karachi", "SITE, Karachi", "021-32567892", "iil@intind.pk", "7890126-6"),
    ("SUP038", "Khyber Tobacco", "Peshawar", "Industrial Estate, Peshawar", "091-23456789", "khyber@khybertobacco.pk", "8901237-7"),
    ("SUP039", "Rafhan Maize Products", "Faisalabad", "Satiana Road, Faisalabad", "041-23456791", "rafhan@rafhan.pk", "9012348-8"),
    ("SUP040", "Shell Pakistan Ltd", "Karachi", "Beaumont Road, Karachi", "021-35640000", "shell.pk@shell.com", "0123459-9"),
    ("SUP041", "Bestway Cement", "Islamabad", "Blue Area, Islamabad", "051-28234567", "bestway@bestway.pk", "1234561-1"),
    ("SUP042", "Colony Mills", "Multan", "Bosan Road, Multan", "061-45234567", "colony@colonymills.pk", "2345672-2"),
    ("SUP043", "Dewan Cement", "Karachi", "Clifton, Karachi", "021-35670001", "dewan@dewancement.pk", "3456783-3"),
    ("SUP044", "Fauji Fertilizer", "Rawalpindi", "Rachna House, Rawalpindi", "051-45678903", "ffc@fauji.pk", "4567894-4"),
    ("SUP045", "Hussain Industries", "Lahore", "Township, Lahore", "042-35129001", "hussain@hussainind.pk", "5678905-5"),
    ("SUP046", "ICI Pakistan Ltd", "Karachi", "5 West Wharf, Karachi", "021-32311000", "ici@ici.com.pk", "6789016-6"),
    ("SUP047", "Jan Muhammad & Sons", "Peshawar", "Chowk Yadgar, Peshawar", "091-23456790", "janmuhammad@gmail.com", "7890127-7"),
    ("SUP048", "Korangi Paper Mills", "Karachi", "Korangi Creek Rd, Karachi", "021-35112346", "kpm@korangipaper.pk", "8901238-8"),
    ("SUP049", "Lahore Chemical Works", "Lahore", "Sundar Industrial Estate", "042-35761235", "lcw@lahorechemical.pk", "9012349-9"),
    ("SUP050", "Metropolitan Steel Corp", "Karachi", "SITE, Karachi", "021-32145680", "msc@metrosteel.pk", "0123450-0"),
    ("SUP051", "Nishat Mills", "Faisalabad", "Nishat Ave, Faisalabad", "041-28901237", "procurement@nishat.pk", "1234562-2"),
    ("SUP052", "Orient Electronics", "Lahore", "Main Boulevard, Lahore", "042-35712341", "orient@orient.com.pk", "2345673-3"),
    ("SUP053", "Premier Systems Ltd", "Islamabad", "G-8 Markaz, Islamabad", "051-28234568", "premier@premier.pk", "3456784-4"),
    ("SUP054", "Qaiser Traders", "Sialkot", "Paris Road, Sialkot", "052-34512781", "qaiser@gmail.com", "4567895-5"),
    ("SUP055", "Rupali Polyester", "Karachi", "Korangi Industrial, Karachi", "021-35814568", "rupali@rupali.pk", "5678906-6"),
]


def seed_suppliers() -> int:
    created_count = 0
    for code, name, city_name, addr1, tel1, email, ntn in SUPPLIERS:
        _, created = Supplier.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "addr1": addr1,
                "tel1": tel1,
                "email": email,
                "ntn_number": ntn,
                "status": STATUS_ACTIVE,
            },
        )
        created_count += int(created)
    return created_count
