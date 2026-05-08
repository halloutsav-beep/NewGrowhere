"""
Curated native-species database with explicit categories (tree / shrub /
ground_cover). Used as the deterministic fallback when the LLM is unavailable
and as the "typical natives" list injected into the LLM prompt when GBIF has
no matches.

Each entry matches the `SpeciesItem` schema plus a ``category`` tag:

    common_name, scientific_name, why, best_planting_window,
    water_needs (low|medium|high), growth_rate (slow|medium|fast),
    biodiversity_value, category (tree|shrub|ground_cover)

Bioregion keys are unchanged from the previous schema to preserve backward
compatibility — only the species rows gained a ``category`` field and extra
shrub / ground_cover rows were added.
"""

from typing import Dict, List
import hashlib


# ---------------------------------------------------------------------------
# Bioregion classifier (lat/lng -> coarse region key)
# ---------------------------------------------------------------------------

def classify_bioregion(lat: float, lng: float) -> str:
    """Return a coarse biogeographic region key.

    Order matters — more specific boxes are checked first so a point doesn't
    accidentally fall into a larger "catch-all" region.
    """
    abs_lat = abs(lat)

    if 6 <= lat <= 37 and 68 <= lng <= 98:
        return "indian_subcontinent"
    if -11 <= lat <= 23 and 92 <= lng <= 141:
        return "southeast_asia"
    if 20 <= lat <= 55 and 100 <= lng <= 146:
        return "east_asia"
    if 12 <= lat <= 42 and 34 <= lng <= 68:
        return "middle_east_arid"
    if -35 <= lat <= 18 and -18 <= lng <= 52:
        return "africa_subsaharan"
    if 28 <= lat <= 46 and -10 <= lng <= 40:
        return "mediterranean"
    if 46 < lat <= 62 and -12 <= lng <= 42:
        return "europe_temperate"
    if abs_lat > 60:
        return "boreal_polar"
    if 25 <= lat <= 60 and -130 <= lng <= -55:
        return "north_america_temperate"
    if 7 <= lat < 25 and -118 <= lng <= -60:
        return "central_america"
    if -56 <= lat <= 12 and -82 <= lng <= -34:
        return "south_america"
    if -47 <= lat <= -9 and 112 <= lng <= 180:
        return "australia_oceania"
    return "tropical_generic"


def climate_zone(lat: float) -> str:
    """Very rough Köppen-style climate band from latitude alone (legacy)."""
    a = abs(lat)
    if a < 10:
        return "equatorial / tropical humid"
    if a < 23.5:
        return "tropical / subtropical"
    if a < 35:
        return "subtropical / mediterranean"
    if a < 50:
        return "temperate"
    if a < 66:
        return "boreal / cold temperate"
    return "polar / alpine"


# ---------------------------------------------------------------------------
# Curated native-species database — now with category tags
# ---------------------------------------------------------------------------

def _tree(d: dict) -> dict:  return {**d, "category": "tree"}
def _shrub(d: dict) -> dict: return {**d, "category": "shrub"}
def _gc(d: dict) -> dict:    return {**d, "category": "ground_cover"}


REGIONAL_SPECIES_DB: Dict[str, List[dict]] = {
    "indian_subcontinent": [
        # Trees
        _tree({"common_name": "Jamun", "scientific_name": "Syzygium cumini",
         "why": "Native riparian hardwood, tolerates seasonal flooding, bird-food tree.",
         "best_planting_window": "June–August (monsoon onset)", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Fruits feed bulbuls, mynahs, bats."}),
        _tree({"common_name": "Arjuna", "scientific_name": "Terminalia arjuna",
         "why": "Riverbank stabiliser with medicinal bark, fast establishing on degraded land.",
         "best_planting_window": "June–July", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Host to moon-moth silk caterpillars."}),
        _tree({"common_name": "Mahua", "scientific_name": "Madhuca longifolia",
         "why": "Drought-hardy and culturally significant, rich nectar for pollinators.",
         "best_planting_window": "July–August", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Nectar source for bees, bats, sloth bear."}),
        _tree({"common_name": "Peepal", "scientific_name": "Ficus religiosa",
         "why": "Keystone urban species, very high insect & bird biodiversity load.",
         "best_planting_window": "June–September", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Fig wasps + 40+ frugivore species."}),
        _tree({"common_name": "Amla", "scientific_name": "Phyllanthus emblica",
         "why": "Small drought-tolerant fruiting tree suited to community orchards.",
         "best_planting_window": "July", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Fruits for parakeets, langurs."}),
        _tree({"common_name": "Bael", "scientific_name": "Aegle marmelos",
         "why": "Sacred native, survives poor soils, provides fruit & shade.",
         "best_planting_window": "July–August", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Host to common Mormon butterfly."}),
        _tree({"common_name": "Kadamba", "scientific_name": "Neolamarckia cadamba",
         "why": "Fast-growing riparian native, rapid canopy for degraded plots.",
         "best_planting_window": "June–July", "water_needs": "high",
         "growth_rate": "fast", "biodiversity_value": "Flowers attract sunbirds, bees."}),
        _tree({"common_name": "Neem", "scientific_name": "Azadirachta indica",
         "why": "Drought-tolerant evergreen generalist, widely native across subcontinent.",
         "best_planting_window": "June–July", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Supports parakeets, carpenter bees."}),
        # Shrubs
        _shrub({"common_name": "Karonda", "scientific_name": "Carissa carandas",
         "why": "Thorny native shrub for live fencing on degraded edges.",
         "best_planting_window": "June–August", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Nesting cover for small passerines."}),
        _shrub({"common_name": "Adhatoda", "scientific_name": "Justicia adhatoda",
         "why": "Hardy medicinal shrub, tolerates degraded soils.",
         "best_planting_window": "June–August", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Carpenter bee and sunbird nectar."}),
        _shrub({"common_name": "Lantana (native)", "scientific_name": "Lantana indica",
         "why": "True native Lantana (not the invasive camara) — butterfly magnet.",
         "best_planting_window": "June–August", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Nectar for 30+ butterfly species."}),
        _shrub({"common_name": "Curry Leaf", "scientific_name": "Murraya koenigii",
         "why": "Small native shrub, culinary + host to swallowtails.",
         "best_planting_window": "June–August", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Common Mormon host plant."}),
        _shrub({"common_name": "Indian Abutilon", "scientific_name": "Abutilon indicum",
         "why": "Native scrub shrub for degraded roadsides.",
         "best_planting_window": "June–September", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Cotton stainer bug + bees host."}),
        # Ground cover
        _gc({"common_name": "Bermuda Grass (Doob)", "scientific_name": "Cynodon dactylon",
         "why": "Native creeping grass, stabilises soil on slopes, drought hardy.",
         "best_planting_window": "June–September", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Larval host for grass skipper butterflies."}),
        _gc({"common_name": "Indian Pennywort", "scientific_name": "Centella asiatica",
         "why": "Shade-tolerant ground mat for moist edges, medicinal native.",
         "best_planting_window": "June–August", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Insect-rich moist-soil ground layer."}),
        _gc({"common_name": "Tephrosia", "scientific_name": "Tephrosia purpurea",
         "why": "Native nitrogen-fixing legume ground cover, soil rehab.",
         "best_planting_window": "July–August", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Blue butterfly (Lycaenidae) host."}),
        _gc({"common_name": "Sida", "scientific_name": "Sida cordifolia",
         "why": "Hardy low shrubby ground cover for arid scrub.",
         "best_planting_window": "July", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Skipper butterfly larval host."}),
    ],
    "southeast_asia": [
        _tree({"common_name": "Meranti", "scientific_name": "Shorea leprosula",
         "why": "Primary rainforest canopy species — restoration keystone for degraded lowland forest.",
         "best_planting_window": "Start of wet season (Apr–Jun)", "water_needs": "high",
         "growth_rate": "medium", "biodiversity_value": "Supports hornbills, orangutans, gibbons."}),
        _tree({"common_name": "Binuang", "scientific_name": "Octomeles sumatrana",
         "why": "Fast pioneer for degraded lowland sites, heals forest gaps quickly.",
         "best_planting_window": "May–July", "water_needs": "high",
         "growth_rate": "fast", "biodiversity_value": "Early-succession habitat for insects, bats."}),
        _tree({"common_name": "Rambutan", "scientific_name": "Nephelium lappaceum",
         "why": "Native fruiting tree ideal for agroforestry restoration.",
         "best_planting_window": "April–June", "water_needs": "high",
         "growth_rate": "medium", "biodiversity_value": "Fruits feed civets, macaques, bats."}),
        _tree({"common_name": "Mangrove (Rhizophora)", "scientific_name": "Rhizophora apiculata",
         "why": "Coastal/estuary restoration, carbon-dense, storm buffer.",
         "best_planting_window": "Year-round tidal planting", "water_needs": "high",
         "growth_rate": "medium", "biodiversity_value": "Fish nursery, wader bird habitat."}),
        _tree({"common_name": "Jackfruit", "scientific_name": "Artocarpus heterophyllus",
         "why": "Large canopy food-tree native to rainforest belt.",
         "best_planting_window": "April–July", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Fruit for gibbons, hornbills."}),
        _tree({"common_name": "Teak", "scientific_name": "Tectona grandis",
         "why": "Monsoon deciduous native, for drier mainland SEA sites.",
         "best_planting_window": "June–August", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Host to leaf-roller moths, birds."}),
        _shrub({"common_name": "Ixora", "scientific_name": "Ixora chinensis",
         "why": "Flowering native shrub, year-round butterfly nectar.",
         "best_planting_window": "April–June", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Swallowtail + sunbird nectar."}),
        _shrub({"common_name": "Malay Rhododendron", "scientific_name": "Melastoma malabathricum",
         "why": "Pioneer shrub for degraded lowland — rapid cover.",
         "best_planting_window": "May–July", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Fruit for bulbuls and barbets."}),
        _shrub({"common_name": "Sandalwood", "scientific_name": "Santalum album",
         "why": "Aromatic native semi-parasite for degraded dryland restoration.",
         "best_planting_window": "June–July", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Host to Lepidoptera."}),
        _gc({"common_name": "Cogon Grass (native form)", "scientific_name": "Imperata cylindrica",
         "why": "Native pioneer grass for degraded clearings (managed).",
         "best_planting_window": "May–July", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Grass-skipper butterfly larval host."}),
        _gc({"common_name": "Sword Fern", "scientific_name": "Nephrolepis biserrata",
         "why": "Shade-loving native ground fern, moisture retention.",
         "best_planting_window": "Rainy season", "water_needs": "high",
         "growth_rate": "medium", "biodiversity_value": "Supports moist-forest invertebrates."}),
        _gc({"common_name": "Asian Pennywort", "scientific_name": "Centella asiatica",
         "why": "Creeping native ground mat for moist edges.",
         "best_planting_window": "May–August", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Ground-layer insect habitat."}),
    ],
    "east_asia": [
        _tree({"common_name": "Japanese Maple", "scientific_name": "Acer palmatum",
         "why": "Temperate understorey native, tolerates urban microclimates.",
         "best_planting_window": "March–April or October", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Supports native moths, cavity nesters."}),
        _tree({"common_name": "Chinese Pistache", "scientific_name": "Pistacia chinensis",
         "why": "Drought-tolerant native ornamental, strong autumn colour.",
         "best_planting_window": "March–April", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Fruits feed winter thrushes."}),
        _tree({"common_name": "Ginkgo", "scientific_name": "Ginkgo biloba",
         "why": "Iconic native relict, extreme pollution tolerance, long-lived urban tree.",
         "best_planting_window": "October–April (dormant)", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Nesting cavities when mature."}),
        _tree({"common_name": "Zelkova", "scientific_name": "Zelkova serrata",
         "why": "Temperate native shade tree, resilient to urban stress.",
         "best_planting_window": "November–March", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Host to native longhorn beetles."}),
        _tree({"common_name": "Korean Fir", "scientific_name": "Abies koreana",
         "why": "Upland conifer native to Korean peninsula & adjacent ranges.",
         "best_planting_window": "March–April", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Winter cover for small mammals & birds."}),
        _tree({"common_name": "Camphor Laurel", "scientific_name": "Cinnamomum camphora",
         "why": "Subtropical evergreen native to S. China / Japan.",
         "best_planting_window": "March–May", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Swallowtail butterfly host."}),
        _shrub({"common_name": "Japanese Camellia", "scientific_name": "Camellia japonica",
         "why": "Evergreen flowering native shrub, shade-tolerant.",
         "best_planting_window": "October–March", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Winter nectar for white-eye birds."}),
        _shrub({"common_name": "Kerria", "scientific_name": "Kerria japonica",
         "why": "Native understory shrub, bright spring bloom.",
         "best_planting_window": "March–April", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Bee pollen in early spring."}),
        _gc({"common_name": "Mondo Grass", "scientific_name": "Ophiopogon japonicus",
         "why": "Shade-loving native ground cover, evergreen mat.",
         "best_planting_window": "March–May", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Shelters ground beetles, small lizards."}),
        _gc({"common_name": "Japanese Pachysandra", "scientific_name": "Pachysandra terminalis",
         "why": "Carpet ground cover for shaded temperate forests.",
         "best_planting_window": "March–April", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Dense litter layer habitat."}),
    ],
    "middle_east_arid": [
        _tree({"common_name": "Ghaf", "scientific_name": "Prosopis cineraria",
         "why": "Arabian/Sindh native, deep taproot, survives extreme drought.",
         "best_planting_window": "October–February", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Shade for desert wildlife, pollinator magnet."}),
        _tree({"common_name": "Sidr", "scientific_name": "Ziziphus spina-christi",
         "why": "Culturally significant arid native, fruit & fodder value.",
         "best_planting_window": "Autumn", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Nectar for bees; host to lycaenid butterflies."}),
        _tree({"common_name": "Date Palm", "scientific_name": "Phoenix dactylifera",
         "why": "Oasis-defining native, excellent for saline/arid degraded land.",
         "best_planting_window": "Spring", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Nesting for desert owls and doves."}),
        _tree({"common_name": "Persian Oak", "scientific_name": "Quercus brantii",
         "why": "Zagros foothill native, restores upland oak woodland.",
         "best_planting_window": "November–February", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Acorns feed wild boar, jays, rodents."}),
        _tree({"common_name": "Carob", "scientific_name": "Ceratonia siliqua",
         "why": "Levantine native, nitrogen-fixing evergreen for dryland restoration.",
         "best_planting_window": "October–March", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Pollinator-friendly winter flowers."}),
        _tree({"common_name": "Samr Acacia", "scientific_name": "Vachellia tortilis",
         "why": "Classic dryland native, fast shade, browse for wildlife.",
         "best_planting_window": "Spring", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Keystone tree for Arabian ungulates."}),
        _shrub({"common_name": "Oleander", "scientific_name": "Nerium oleander",
         "why": "Heat/saline tolerant native shrub for road corridors (non-edible).",
         "best_planting_window": "Year-round (mild season)", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Hawk-moth nectar source."}),
        _shrub({"common_name": "Calligonum", "scientific_name": "Calligonum comosum",
         "why": "Native dune-stabilising shrub for sandy desert restoration.",
         "best_planting_window": "Autumn", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Cover for sand-dwelling lizards."}),
        _shrub({"common_name": "Indigofera", "scientific_name": "Indigofera articulata",
         "why": "Native legume shrub, nitrogen-fixing on degraded hamada.",
         "best_planting_window": "Spring", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Blue butterfly host plant."}),
        _gc({"common_name": "Saltbush", "scientific_name": "Atriplex halimus",
         "why": "Salt-tolerant native ground shrub, soil rehab for saline sites.",
         "best_planting_window": "Autumn", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Cover for desert rodents."}),
        _gc({"common_name": "Desert Grass", "scientific_name": "Panicum turgidum",
         "why": "Hardy native perennial grass, sand-binding ground layer.",
         "best_planting_window": "Autumn rains", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Forage for Arabian oryx, gazelles."}),
    ],
    "africa_subsaharan": [
        _tree({"common_name": "Baobab", "scientific_name": "Adansonia digitata",
         "why": "Iconic savanna native, stores water, keystone for dry biomes.",
         "best_planting_window": "Early rains (Nov–Jan)", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Nectar for bats; nesting for hornbills."}),
        _tree({"common_name": "Umbrella Thorn", "scientific_name": "Vachellia tortilis",
         "why": "Savanna native, fast shade on degraded rangeland.",
         "best_planting_window": "Start of rains", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Giraffe browse; weaver-bird nests."}),
        _tree({"common_name": "African Mahogany", "scientific_name": "Khaya senegalensis",
         "why": "Miombo / Sudanian native hardwood, shade + soil improvement.",
         "best_planting_window": "April–June", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Host to endemic longhorn beetles."}),
        _tree({"common_name": "Marula", "scientific_name": "Sclerocarya birrea",
         "why": "Savanna native, fruit for wildlife and communities.",
         "best_planting_window": "November–December", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Elephants, kudu, birds feed on fruit."}),
        _tree({"common_name": "Shea", "scientific_name": "Vitellaria paradoxa",
         "why": "Sudanian zone native, key agroforestry species.",
         "best_planting_window": "May–July", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Flowers feed honeybees (shea honey)."}),
        _tree({"common_name": "Yellow Fever Acacia", "scientific_name": "Vachellia xanthophloea",
         "why": "Riparian / floodplain native, rapid restoration of wetlands.",
         "best_planting_window": "Start of rains", "water_needs": "high",
         "growth_rate": "fast", "biodiversity_value": "Vervet monkey & heron roost."}),
        _shrub({"common_name": "Hibiscus (native)", "scientific_name": "Hibiscus fuscus",
         "why": "Native flowering shrub, sunbird magnet.",
         "best_planting_window": "Early rains", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Sunbird nectar, bee pollen."}),
        _shrub({"common_name": "Kei Apple", "scientific_name": "Dovyalis caffra",
         "why": "Native thorny hedge shrub, wildlife food + living fence.",
         "best_planting_window": "Start of rains", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Fruit for bushbabies and francolins."}),
        _gc({"common_name": "Buffalo Grass", "scientific_name": "Panicum maximum",
         "why": "Robust native grass for savanna ground cover restoration.",
         "best_planting_window": "Start of rains", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Grass-eating antelope forage."}),
        _gc({"common_name": "Carpet Grass", "scientific_name": "Digitaria eriantha",
         "why": "Native dense mat grass for degraded rangeland.",
         "best_planting_window": "Early rains", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Ground-nesting bird habitat."}),
    ],
    "mediterranean": [
        _tree({"common_name": "Cork Oak", "scientific_name": "Quercus suber",
         "why": "Iberian/N.Africa native, fire-resilient, soil-building.",
         "best_planting_window": "November–February", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Acorns for Iberian lynx prey species."}),
        _tree({"common_name": "Holm Oak", "scientific_name": "Quercus ilex",
         "why": "Classic Mediterranean evergreen oak for dehesa restoration.",
         "best_planting_window": "November–February", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Keystone for cavity nesters & acorn eaters."}),
        _tree({"common_name": "Stone Pine", "scientific_name": "Pinus pinea",
         "why": "Umbrella-crown Mediterranean native, fire-tolerant.",
         "best_planting_window": "October–March", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Pine nuts for jays, squirrels."}),
        _tree({"common_name": "Aleppo Pine", "scientific_name": "Pinus halepensis",
         "why": "Degraded maquis & limestone native, drought hardy.",
         "best_planting_window": "November–February", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Crossbill + processionary moth host."}),
        _tree({"common_name": "Carob", "scientific_name": "Ceratonia siliqua",
         "why": "Native legume, drought-proof, fodder + human food.",
         "best_planting_window": "October–March", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Winter bee nectar."}),
        _shrub({"common_name": "Strawberry Tree", "scientific_name": "Arbutus unedo",
         "why": "Evergreen native shrub-tree, excellent winter nectar source.",
         "best_planting_window": "Autumn", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Pollinators + frugivorous birds."}),
        _shrub({"common_name": "Mastic", "scientific_name": "Pistacia lentiscus",
         "why": "Drought-hardy native shrub for early succession.",
         "best_planting_window": "Autumn", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Fruits for warblers & sylvias."}),
        _shrub({"common_name": "Rosemary", "scientific_name": "Salvia rosmarinus",
         "why": "Iconic Mediterranean native shrub, pollinator beacon.",
         "best_planting_window": "Autumn", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Winter bee nectar."}),
        _gc({"common_name": "Thyme", "scientific_name": "Thymus vulgaris",
         "why": "Aromatic low-growing native ground cover for rocky slopes.",
         "best_planting_window": "Autumn–spring", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Essential pollinator nectar."}),
        _gc({"common_name": "Cistus", "scientific_name": "Cistus albidus",
         "why": "Drought-hardy native rock-rose mat for degraded garrigue.",
         "best_planting_window": "Autumn", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Host to cistus-specific bees."}),
    ],
    "europe_temperate": [
        _tree({"common_name": "English Oak", "scientific_name": "Quercus robur",
         "why": "Temperate keystone — supports >400 invertebrate species.",
         "best_planting_window": "November–March (dormant)", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Massive entomofauna + cavity nesters."}),
        _tree({"common_name": "Silver Birch", "scientific_name": "Betula pendula",
         "why": "Pioneer native for degraded / acidic soils.",
         "best_planting_window": "November–March", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Host to >300 insect species."}),
        _tree({"common_name": "Rowan", "scientific_name": "Sorbus aucuparia",
         "why": "Hardy upland native, winter berries for thrushes.",
         "best_planting_window": "November–March", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Redwing & fieldfare food."}),
        _tree({"common_name": "Small-leaved Lime", "scientific_name": "Tilia cordata",
         "why": "Ancient woodland native, excellent urban shade.",
         "best_planting_window": "November–March", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Massive nectar flow for bees."}),
        _tree({"common_name": "Wild Cherry", "scientific_name": "Prunus avium",
         "why": "Native pioneer with spring bloom & summer fruit.",
         "best_planting_window": "November–March", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Early pollinator nectar; bird fruit."}),
        _tree({"common_name": "Alder", "scientific_name": "Alnus glutinosa",
         "why": "Riparian nitrogen-fixer, stabilises degraded wet soils.",
         "best_planting_window": "November–February", "water_needs": "high",
         "growth_rate": "fast", "biodiversity_value": "Otter / kingfisher bank cover."}),
        _shrub({"common_name": "Hazel", "scientific_name": "Corylus avellana",
         "why": "Coppice-friendly native shrub, understorey diversity.",
         "best_planting_window": "November–March", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Dormouse keystone species."}),
        _shrub({"common_name": "Hawthorn", "scientific_name": "Crataegus monogyna",
         "why": "Classic native hedge shrub, wildlife food.",
         "best_planting_window": "November–March", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Bird fruit + nesting cover."}),
        _shrub({"common_name": "Blackthorn", "scientific_name": "Prunus spinosa",
         "why": "Early-blooming native hedge shrub for pollinators.",
         "best_planting_window": "November–March", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Brown hairstreak butterfly host."}),
        _gc({"common_name": "Wild Strawberry", "scientific_name": "Fragaria vesca",
         "why": "Native creeping ground cover, fruit for wildlife.",
         "best_planting_window": "March–April", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Bumblebees + bird fruit."}),
        _gc({"common_name": "Wood Anemone", "scientific_name": "Anemone nemorosa",
         "why": "Ancient woodland indicator ground flora.",
         "best_planting_window": "Autumn (bulbs)", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Early-spring pollinator nectar."}),
        _gc({"common_name": "Bugle", "scientific_name": "Ajuga reptans",
         "why": "Native mat-forming ground cover for damp edges.",
         "best_planting_window": "Autumn–spring", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Early bumblebee nectar."}),
    ],
    "boreal_polar": [
        _tree({"common_name": "Scots Pine", "scientific_name": "Pinus sylvestris",
         "why": "Widely native conifer, tolerates poor soils & cold.",
         "best_planting_window": "May or September", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Capercaillie, crossbill habitat."}),
        _tree({"common_name": "Siberian Larch", "scientific_name": "Larix sibirica",
         "why": "Boreal deciduous conifer, extreme cold hardy.",
         "best_planting_window": "May", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Winter browse for moose."}),
        _tree({"common_name": "White Spruce", "scientific_name": "Picea glauca",
         "why": "Boreal keystone, cold hardy, slow mature cover.",
         "best_planting_window": "Spring / early autumn", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Spruce grouse & marten habitat."}),
        _tree({"common_name": "Downy Birch", "scientific_name": "Betula pubescens",
         "why": "Boreal pioneer on wet / acidic soils.",
         "best_planting_window": "May or September", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Redpoll, willow warbler habitat."}),
        _tree({"common_name": "Aspen", "scientific_name": "Populus tremula",
         "why": "Fast clonal native, critical for deadwood biodiversity.",
         "best_planting_window": "Spring", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Beaver forage; woodpecker hosts."}),
        _shrub({"common_name": "Willow (dwarf)", "scientific_name": "Salix lapponum",
         "why": "Boreal native shrub willow for wetland edges.",
         "best_planting_window": "May", "water_needs": "high",
         "growth_rate": "medium", "biodiversity_value": "Early pollen for bumblebees."}),
        _shrub({"common_name": "Bog Myrtle", "scientific_name": "Myrica gale",
         "why": "Native peatland shrub, nitrogen-fixing.",
         "best_planting_window": "Spring", "water_needs": "high",
         "growth_rate": "medium", "biodiversity_value": "Aromatic shelter for moths."}),
        _gc({"common_name": "Bilberry", "scientific_name": "Vaccinium myrtillus",
         "why": "Boreal native ground berry, carpet cover.",
         "best_planting_window": "Spring", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Berry for capercaillie, grouse, bears."}),
        _gc({"common_name": "Reindeer Lichen", "scientific_name": "Cladonia rangiferina",
         "why": "Characteristic boreal ground layer — slow but keystone.",
         "best_planting_window": "N/A (natural recruitment)", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Primary winter forage for reindeer."}),
    ],
    "north_america_temperate": [
        _tree({"common_name": "Eastern Red Oak", "scientific_name": "Quercus rubra",
         "why": "Temperate keystone, acorn mast for wildlife.",
         "best_planting_window": "October–April (dormant)", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Host to 500+ Lepidoptera species."}),
        _tree({"common_name": "Sugar Maple", "scientific_name": "Acer saccharum",
         "why": "Eastern native, shade-tolerant climax canopy.",
         "best_planting_window": "November–March", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Cavity nester haven when mature."}),
        _tree({"common_name": "Eastern White Pine", "scientific_name": "Pinus strobus",
         "why": "Soft pine native, fast cover for degraded NE forests.",
         "best_planting_window": "March–May", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Pine warbler, osprey nesting."}),
        _tree({"common_name": "Black Cherry", "scientific_name": "Prunus serotina",
         "why": "Native fruiting pioneer, bird-distributed.",
         "best_planting_window": "November–March", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Tiger swallowtail host; bird fruit."}),
        _tree({"common_name": "American Sycamore", "scientific_name": "Platanus occidentalis",
         "why": "Riparian giant, streambank restoration.",
         "best_planting_window": "Late winter", "water_needs": "high",
         "growth_rate": "fast", "biodiversity_value": "Wood-duck cavity habitat."},
        ),
        _tree({"common_name": "Douglas-fir", "scientific_name": "Pseudotsuga menziesii",
         "why": "West-coast / Rocky Mountain native conifer.",
         "best_planting_window": "November–March", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Spotted owl + marbled murrelet habitat."}),
        _shrub({"common_name": "Eastern Redbud", "scientific_name": "Cercis canadensis",
         "why": "Small understory native, early spring pollinator bloom.",
         "best_planting_window": "November–March", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Bumblebee early nectar."}),
        _shrub({"common_name": "Serviceberry", "scientific_name": "Amelanchier canadensis",
         "why": "Native multi-stem shrub, spring bloom + summer fruit.",
         "best_planting_window": "October–April", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Early-bee nectar + bird fruit."}),
        _shrub({"common_name": "Spicebush", "scientific_name": "Lindera benzoin",
         "why": "Understory native shrub for eastern moist forests.",
         "best_planting_window": "October–April", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Spicebush swallowtail host."}),
        _gc({"common_name": "Wild Ginger", "scientific_name": "Asarum canadense",
         "why": "Forest-floor native mat for shaded temperate woodland.",
         "best_planting_window": "March–April", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Ant seed dispersal (myrmecochory)."}),
        _gc({"common_name": "Pennsylvania Sedge", "scientific_name": "Carex pensylvanica",
         "why": "Native shade-tolerant sedge for woodland ground layer.",
         "best_planting_window": "March–May", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Larval host for skipper butterflies."}),
    ],
    "central_america": [
        _tree({"common_name": "Ceiba / Kapok", "scientific_name": "Ceiba pentandra",
         "why": "Emergent rainforest native, cultural keystone.",
         "best_planting_window": "May–July", "water_needs": "high",
         "growth_rate": "fast", "biodiversity_value": "Bat-pollinated; macaw nesting."}),
        _tree({"common_name": "Guanacaste", "scientific_name": "Enterolobium cyclocarpum",
         "why": "Dry-forest native legume, excellent shade/fodder.",
         "best_planting_window": "May–June", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Seeds for tapirs, peccaries."}),
        _tree({"common_name": "Madre de Cacao", "scientific_name": "Gliricidia sepium",
         "why": "Nitrogen-fixing native for agroforestry coffee/cacao.",
         "best_planting_window": "Early rains", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Hummingbird nectar in dry season."}),
        _tree({"common_name": "Mexican Mahogany", "scientific_name": "Swietenia humilis",
         "why": "Pacific dry-forest native (threatened).",
         "best_planting_window": "May", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Host to parrot species."}),
        _tree({"common_name": "Calabash Tree", "scientific_name": "Crescentia cujete",
         "why": "Savanna native, bat-pollinated, cultural use.",
         "best_planting_window": "May–July", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Nectar-feeding bats."}),
        _shrub({"common_name": "Hamelia", "scientific_name": "Hamelia patens",
         "why": "Native flowering shrub, hummingbird magnet.",
         "best_planting_window": "Early rains", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Hummingbird & butterfly nectar."}),
        _shrub({"common_name": "Firebush Cordia", "scientific_name": "Cordia sebestena",
         "why": "Native coastal shrub-tree, salt hardy.",
         "best_planting_window": "May–June", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Butterfly + bird nectar."}),
        _gc({"common_name": "Frog Fruit", "scientific_name": "Phyla nodiflora",
         "why": "Creeping native mat, butterfly host.",
         "best_planting_window": "Early rains", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "White peacock butterfly host."}),
        _gc({"common_name": "Tropical Sage", "scientific_name": "Salvia coccinea",
         "why": "Native ground cover flowering species, hummingbird nectar.",
         "best_planting_window": "May", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Hummingbird nectar."}),
    ],
    "south_america": [
        _tree({"common_name": "Guanandi", "scientific_name": "Calophyllum brasiliense",
         "why": "Atlantic Forest / Amazonian riparian native.",
         "best_planting_window": "October–December", "water_needs": "high",
         "growth_rate": "medium", "biodiversity_value": "Fruits for parrots; wet-forest bird refuge."}),
        _tree({"common_name": "Jequitibá", "scientific_name": "Cariniana legalis",
         "why": "Emergent Atlantic Forest giant, keystone canopy.",
         "best_planting_window": "October–January", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Harpy eagle & toucan habitat."}),
        _tree({"common_name": "Ipê-amarelo", "scientific_name": "Handroanthus albus",
         "why": "Iconic Cerrado/ Atlantic native, fire-resilient.",
         "best_planting_window": "October–December", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Nectar for hummingbirds in dry season."}),
        _tree({"common_name": "Pau-brasil", "scientific_name": "Paubrasilia echinata",
         "why": "Critically endangered Atlantic Forest native — restoration priority.",
         "best_planting_window": "October–January", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Lepidoptera host; bee-pollinated."}),
        _tree({"common_name": "Brazil Nut", "scientific_name": "Bertholletia excelsa",
         "why": "Amazonian emergent, agouti + orchid-bee mutualism.",
         "best_planting_window": "October–December", "water_needs": "high",
         "growth_rate": "medium", "biodiversity_value": "Requires orchid bees & agoutis."}),
        _tree({"common_name": "Jatobá", "scientific_name": "Hymenaea courbaril",
         "why": "Dry-forest & cerrado native, long-lived hardwood.",
         "best_planting_window": "October–December", "water_needs": "low",
         "growth_rate": "slow", "biodiversity_value": "Fruits for agoutis; bat pollination."}),
        _tree({"common_name": "Araucaria", "scientific_name": "Araucaria angustifolia",
         "why": "Endemic southern Brazil / Argentina conifer (endangered).",
         "best_planting_window": "September–November", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Araucaria pine nuts feed parrots."}),
        _shrub({"common_name": "Pitanga", "scientific_name": "Eugenia uniflora",
         "why": "Native Atlantic Forest fruiting shrub.",
         "best_planting_window": "October–December", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Fruit for thrushes; bee-pollinated."}),
        _shrub({"common_name": "Jurubeba", "scientific_name": "Solanum paniculatum",
         "why": "Native cerrado shrub, pollinator-rich white flowers.",
         "best_planting_window": "Early rains", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Bee & moth pollinator hub."}),
        _gc({"common_name": "Grama-São-Carlos", "scientific_name": "Axonopus compressus",
         "why": "Native sod-forming grass for cerrado restoration.",
         "best_planting_window": "Early rains", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Seed-eating finch forage."}),
    ],
    "australia_oceania": [
        _tree({"common_name": "River Red Gum", "scientific_name": "Eucalyptus camaldulensis",
         "why": "Iconic Australian riparian native — restores waterways.",
         "best_planting_window": "Autumn (Apr–May)", "water_needs": "high",
         "growth_rate": "fast", "biodiversity_value": "Hollows for cockatoos, gliders."}),
        _tree({"common_name": "Coolabah", "scientific_name": "Eucalyptus coolabah",
         "why": "Arid-zone native, floodplain & channel country.",
         "best_planting_window": "Autumn", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Hollow-nesting parrots & bats."}),
        _tree({"common_name": "Grey Box", "scientific_name": "Eucalyptus microcarpa",
         "why": "Box-ironbark native for temperate woodland restoration.",
         "best_planting_window": "Autumn", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Swift parrot & regent honeyeater food."}),
        _tree({"common_name": "Pohutukawa", "scientific_name": "Metrosideros excelsa",
         "why": "NZ coastal native, salt/wind hardy.",
         "best_planting_window": "Autumn (Mar–May)", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Tūī & bellbird nectar."}),
        _tree({"common_name": "Kauri", "scientific_name": "Agathis australis",
         "why": "NZ iconic conifer; biosecure plantings only.",
         "best_planting_window": "Autumn", "water_needs": "medium",
         "growth_rate": "slow", "biodiversity_value": "Hosts endemic kauri snails & weta."}),
        _shrub({"common_name": "Silver Wattle", "scientific_name": "Acacia dealbata",
         "why": "Native nitrogen fixer — pioneer for degraded SE Australia sites.",
         "best_planting_window": "Autumn–Winter", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Nectar for honeyeaters; bee pollen."}),
        _shrub({"common_name": "Sheoak", "scientific_name": "Allocasuarina verticillata",
         "why": "Hardy native, food for glossy black-cockatoos.",
         "best_planting_window": "Autumn", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Glossy black-cockatoo keystone."}),
        _shrub({"common_name": "Bottlebrush", "scientific_name": "Callistemon citrinus",
         "why": "Native flowering shrub, honeyeater nectar magnet.",
         "best_planting_window": "Autumn", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Honeyeater keystone nectar."}),
        _gc({"common_name": "Kangaroo Grass", "scientific_name": "Themeda triandra",
         "why": "Iconic native tussock grass for grassland restoration.",
         "best_planting_window": "Autumn", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Key butterfly larval host."}),
        _gc({"common_name": "Wallaby Grass", "scientific_name": "Rytidosperma caespitosum",
         "why": "Native perennial tussock for temperate grassland.",
         "best_planting_window": "Autumn", "water_needs": "low",
         "growth_rate": "medium", "biodiversity_value": "Ground-nesting bird cover."}),
    ],
    "tropical_generic": [
        _tree({"common_name": "Moringa", "scientific_name": "Moringa oleifera",
         "why": "Fast-growing tropical tree, drought-hardy, nutritional pods.",
         "best_planting_window": "Early rains", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Nectar for bees; early pioneer."}),
        _tree({"common_name": "Coconut Palm", "scientific_name": "Cocos nucifera",
         "why": "Pantropical coastal staple, salt-tolerant.",
         "best_planting_window": "Start of rains", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Nesting palms for shorebirds."}),
        _tree({"common_name": "Sea Almond", "scientific_name": "Terminalia catappa",
         "why": "Coastal tropical native, rapid shade, salt hardy.",
         "best_planting_window": "Start of rains", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Fruits for fruit-bats & hermit crabs."}),
        _tree({"common_name": "Breadfruit", "scientific_name": "Artocarpus altilis",
         "why": "Pacific-origin food tree for agroforestry atolls.",
         "best_planting_window": "Start of rains", "water_needs": "high",
         "growth_rate": "medium", "biodiversity_value": "Bat & bird fruit source."}),
        _tree({"common_name": "Casuarina", "scientific_name": "Casuarina equisetifolia",
         "why": "Coastal pioneer, nitrogen fixer on degraded sand.",
         "best_planting_window": "Start of rains", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Windbreak cover for shorebirds."}),
        _shrub({"common_name": "Hibiscus", "scientific_name": "Hibiscus tiliaceus",
         "why": "Coastal tropical native shrub-tree, salt hardy.",
         "best_planting_window": "Start of rains", "water_needs": "medium",
         "growth_rate": "fast", "biodiversity_value": "Coastal bird nesting cover."}),
        _shrub({"common_name": "Native Ixora", "scientific_name": "Ixora coccinea",
         "why": "Tropical flowering native shrub, pollinator magnet.",
         "best_planting_window": "Start of rains", "water_needs": "medium",
         "growth_rate": "medium", "biodiversity_value": "Butterfly nectar."}),
        _gc({"common_name": "Wedelia", "scientific_name": "Sphagneticola trilobata",
         "why": "Tropical creeping native (use local genotype only).",
         "best_planting_window": "Start of rains", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Butterfly nectar ground cover."}),
        _gc({"common_name": "Beach Morning Glory", "scientific_name": "Ipomoea pes-caprae",
         "why": "Tropical beach native, sand-binding ground vine.",
         "best_planting_window": "Year-round", "water_needs": "low",
         "growth_rate": "fast", "biodiversity_value": "Beach-ground invertebrate habitat."}),
    ],
}


# ---------------------------------------------------------------------------
# Deterministic category-aware picker
# ---------------------------------------------------------------------------

def _hash32(*parts: str) -> int:
    key = "|".join(parts)
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


def _by_category(pool: List[dict]) -> Dict[str, List[dict]]:
    buckets: Dict[str, List[dict]] = {"tree": [], "shrub": [], "ground_cover": []}
    for sp in pool:
        cat = sp.get("category", "tree")
        buckets.setdefault(cat, []).append(sp)
    return buckets


def pick_species(lat: float, lng: float, region: str, count: int = 4) -> List[dict]:
    """Back-compat flat picker — returns ``count`` picks total.

    Kept for callers that still want a flat list; new code should use
    :func:`pick_species_categorised`.
    """
    pool = REGIONAL_SPECIES_DB.get(region) or REGIONAL_SPECIES_DB["tropical_generic"]
    if count >= len(pool):
        return list(pool)
    glat = round(lat, 2)
    glng = round(lng, 2)
    indexed = [
        (_hash32(f"{glat}", f"{glng}", sp["scientific_name"], region), sp)
        for sp in pool
    ]
    indexed.sort(key=lambda x: x[0])
    return [sp for _, sp in indexed[:count]]


def pick_species_categorised(
    lat: float, lng: float, region: str,
    trees: int = 6, shrubs: int = 5, ground_cover: int = 4,
) -> Dict[str, List[dict]]:
    """Return species bucketed by category with weighted deterministic variation.

    Same (lat, lng) ⇒ same three lists (cached by grid snap at ~0.01 deg).
    Different grid cells ⇒ different subsets + ordering because the seed is
    derived from the grid key.
    """
    pool = REGIONAL_SPECIES_DB.get(region) or REGIONAL_SPECIES_DB["tropical_generic"]
    buckets = _by_category(pool)

    glat = round(lat, 2)
    glng = round(lng, 2)

    targets = {"tree": trees, "shrub": shrubs, "ground_cover": ground_cover}
    out: Dict[str, List[dict]] = {}
    for cat, n in targets.items():
        cat_pool = buckets.get(cat) or []
        if not cat_pool:
            out[cat] = []
            continue
        # Deterministic shuffle per-cell per-category
        indexed = [
            (_hash32(f"{glat}", f"{glng}", cat, sp["scientific_name"], region), sp)
            for sp in cat_pool
        ]
        indexed.sort(key=lambda x: x[0])
        out[cat] = [sp for _, sp in indexed[:n]]
    return out
