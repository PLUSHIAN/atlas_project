from dataclasses import dataclass
from datetime import date, timedelta

START = date(2027, 9, 8)
END = date(2027, 9, 27)
DAYS = 17
ORIGIN_GROUPS = {"São Paulo": ("GRU", "CGH", "VCP"), "Rio de Janeiro": ("GIG", "SDU")}
DEST_GROUPS = {"Roma": ("FCO",), "Milão": ("MXP", "BGY", "LIN"), "Barcelona": ("BCN",), "Madri": ("MAD",)}
ALL_ORIGINS = tuple(a for airports in ORIGIN_GROUPS.values() for a in airports)
ALL_DESTINATIONS = tuple(a for airports in DEST_GROUPS.values() for a in airports)

@dataclass(frozen=True)
class Route:
    origins: tuple[str, ...]
    destinations: tuple[str, ...]
    departure: date
    return_departure: date

    @property
    def key(self) -> str:
        return f"{','.join(self.origins)}|{','.join(self.destinations)}|{self.departure}|{self.return_departure}"

    @property
    def city(self) -> str:
        return next(k for k, v in DEST_GROUPS.items() if self.destinations == v)


def days_inclusive(departure: date, arrival_home: date) -> int:
    return (arrival_home - departure).days + 1


def is_valid_trip(departure: date, arrival_home: date) -> bool:
    return START <= departure <= arrival_home <= END and days_inclusive(departure, arrival_home) == DAYS


def routes() -> list[Route]:
    """Rotação balanceada. Retorno parte da Europa em D+15 ou D+16;
    apenas chegada final ao Brasil em D+16 torna o voo válido."""
    result = []
    for offset in range(4):
        dep = START + timedelta(days=offset)
        for city, destinations in DEST_GROUPS.items():
            for origins in ORIGIN_GROUPS.values():
                for delta in (15, 16):
                    ret = dep + timedelta(days=delta)
                    if ret <= END:
                        result.append(Route(origins, destinations, dep, ret))
    return result


def find_route(key: str) -> Route:
    for route in routes():
        if route.key == key:
            return route
    raise ValueError("Rota inválida")


def classification(price_couple: float) -> str:
    if price_couple <= 0:
        raise ValueError("Preço inválido")
    if price_couple <= 6000:
        return "EXCELENTE OPORTUNIDADE"
    if price_couple <= 8000:
        return "DENTRO DO ORÇAMENTO"
    return "ACIMA DO ORÇAMENTO"

@dataclass(frozen=True)
class OpenJawRoute:
    """Bilhete internacional multidestinos com duas pernas, Itália entrada/saída.

    A viagem interna entre as duas cidades NÃO faz parte da tarifa aérea.
    """
    origins: tuple[str, ...]
    destinations: tuple[str, ...]
    return_origins: tuple[str, ...]
    departure: date
    return_departure: date

    @property
    def key(self) -> str:
        return (f"OJ|{','.join(self.origins)}|{','.join(self.destinations)}|"
                f"{','.join(self.return_origins)}|{self.departure}|{self.return_departure}")

    @property
    def city(self) -> str:
        entry = next(k for k, a in DEST_GROUPS.items() if a == self.destinations)
        exit_city = next(k for k, a in DEST_GROUPS.items() if a == self.return_origins)
        return f'{entry} → {exit_city}'


OPEN_JAW_CITIES = ('Roma → Milão', 'Milão → Roma')
SEARCH_CITIES = tuple(DEST_GROUPS) + OPEN_JAW_CITIES


def open_jaw_routes() -> list[OpenJawRoute]:
    """Duas direções Itália, mesmos limites de datas e origens de routes()."""
    result = []
    for offset in range(4):
        dep = START + timedelta(days=offset)
        for entry, exit_city in (('Roma', 'Milão'), ('Milão', 'Roma')):
            for origins in ORIGIN_GROUPS.values():
                for delta in (15, 16):
                    ret = dep + timedelta(days=delta)
                    if ret <= END:
                        result.append(OpenJawRoute(origins, DEST_GROUPS[entry],
                                                   DEST_GROUPS[exit_city], dep, ret))
    return result


def all_routes(include_open_jaw=True) -> list[Route | OpenJawRoute]:
    return routes() + (open_jaw_routes() if include_open_jaw else [])
