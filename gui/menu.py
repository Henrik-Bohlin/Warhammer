import pygame 
import sys

def show_movement_menu(screen, font):
    """
    Display a menu for the user to select movement distance in inches.
    Returns the selected value (float).
    """
    options = [5, 6, 7]
    selected = 1  # default to 6

    while True:
        screen.fill((30, 30, 30))

        title = font.render("Select movement (inches):", True, (255, 255, 255))
        screen.blit(title, (50, 50))

        for i, val in enumerate(options):
            color = (255, 200, 0) if i == selected else (200, 200, 200)
            text = font.render(f"{val} inches", True, color)
            screen.blit(text, (50, 120 + i * 50))

        hint = font.render("Use UP/DOWN arrows, ENTER to confirm", True, (150, 150, 150))
        screen.blit(hint, (50, 500))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(options)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(options)
                elif event.key == pygame.K_RETURN:
                    return options[selected]

        pygame.display.flip()