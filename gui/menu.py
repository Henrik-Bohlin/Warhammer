import pygame
import sys

def _quit_game():
    pygame.quit()
    sys.exit()


def show_map_menu(screen, font, maps, map_order):
    """Display a menu for the user to select a map layout. Returns the chosen key."""
    selected = 0
    W, H = screen.get_width(), screen.get_height()

    while True:
        screen.fill((30, 30, 30))

        title = font.render("Select map layout:", True, (255, 255, 255))
        screen.blit(title, (W // 2 - title.get_width() // 2, H // 2 - 80))

        for i, key in enumerate(map_order):
            color = (255, 200, 0) if i == selected else (200, 200, 200)
            text = font.render(maps[key].name, True, color)
            screen.blit(text, (W // 2 - text.get_width() // 2, H // 2 - 20 + i * 50))

        hint = font.render("UP/DOWN: select   ENTER: confirm   Q: quit", True, (150, 150, 150))
        screen.blit(hint, (W // 2 - hint.get_width() // 2, H // 2 + 120))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _quit_game()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(map_order)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(map_order)
                elif event.key == pygame.K_RETURN:
                    return map_order[selected]
                elif event.key == pygame.K_q:
                    _quit_game()

        pygame.display.flip()


def show_movement_menu(screen, font):
    """
    Display a menu for the user to select movement distance in inches.
    Returns the selected value (float).
    """
    options = [5, 6, 7]
    selected = 1  # default to 6
    W, H = screen.get_width(), screen.get_height()

    while True:
        screen.fill((30, 30, 30))

        title = font.render("Select movement (inches):", True, (255, 255, 255))
        screen.blit(title, (W // 2 - title.get_width() // 2, H // 2 - 80))

        for i, val in enumerate(options):
            color = (255, 200, 0) if i == selected else (200, 200, 200)
            text = font.render(f"{val} inches", True, color)
            screen.blit(text, (W // 2 - text.get_width() // 2, H // 2 - 20 + i * 50))

        hint = font.render("UP/DOWN: select   ENTER: confirm   Q: quit", True, (150, 150, 150))
        screen.blit(hint, (W // 2 - hint.get_width() // 2, H // 2 + 120))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _quit_game()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(options)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(options)
                elif event.key == pygame.K_RETURN:
                    return options[selected]
                elif event.key == pygame.K_q:
                    _quit_game()

        pygame.display.flip()